#include "libslic3r/LetterMode/Template.hpp"

#include <algorithm>
#include <cstdio>
#include <fstream>

namespace Slic3r {
namespace LetterMode {
namespace {

[[noreturn]] void fail(const std::string &what) { throw TemplateError(what); }

std::string number_to_text(double value)
{
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "%.17g", value);
    return buffer;
}

const nlohmann::json &require_member(const nlohmann::json &document, const char *key)
{
    const auto it = document.find(key);
    if (it == document.end())
        fail(std::string("letter template is missing the required '") + key + "' member");
    return *it;
}

std::string read_identity(const nlohmann::json &document, const char *key, bool required)
{
    const auto it = document.find(key);
    if (it == document.end()) {
        if (required)
            fail(std::string("letter template is missing the required '") + key + "' member");
        return {};
    }
    if (!it->is_string())
        fail(std::string("letter template member '") + key + "' must be a string");
    const std::string value = it->get<std::string>();
    if (required && value.empty())
        fail(std::string("letter template member '") + key + "' must not be empty");
    return value;
}

} // namespace

nlohmann::json LetterTemplate::to_json() const
{
    if (machine_id.empty())
        fail("letter template has an empty machine_id; a template without a machine identity cannot be saved");

    nlohmann::json document    = nlohmann::json::object();
    document["schema"]         = TEMPLATE_SCHEMA;
    document["version"]        = TEMPLATE_VERSION;
    document["machine_id"]     = machine_id;
    if (!profile_id.empty())
        document["profile_id"] = profile_id;
    document["parameters"]     = parameters;
    return document;
}

LetterTemplate LetterTemplate::from_json(const nlohmann::json &document, const LoadOptions &options)
{
    if (!document.is_object())
        fail("letter template root must be a JSON object");

    const nlohmann::json &schema = require_member(document, "schema");
    if (!schema.is_string() || schema.get<std::string>() != TEMPLATE_SCHEMA)
        fail("not a Letter Mode template: expected schema '" + std::string(TEMPLATE_SCHEMA) + "', found " +
             (schema.is_string() ? "'" + schema.get<std::string>() + "'" : schema.dump()));

    const nlohmann::json &version = require_member(document, "version");
    if (!version.is_number_integer() && !version.is_number_unsigned())
        fail("letter template 'version' must be an integer");
    const long long found_version = version.get<long long>();
    if (found_version != TEMPLATE_VERSION)
        fail("unsupported letter template version " + std::to_string(found_version) + "; this build reads version " +
             std::to_string(TEMPLATE_VERSION) + " only (no silent downgrade)");

    LetterTemplate result;
    result.machine_id = read_identity(document, "machine_id", true);
    result.profile_id = read_identity(document, "profile_id", false);

    if (!options.expected_machine_id.empty() && result.machine_id != options.expected_machine_id)
        fail("letter template belongs to machine '" + result.machine_id + "', not '" + options.expected_machine_id + "'");
    if (!options.expected_profile_id.empty() && !result.profile_id.empty() && result.profile_id != options.expected_profile_id)
        fail("letter template was authored against profile '" + result.profile_id + "', not '" + options.expected_profile_id + "'");

    const nlohmann::json &parameters = require_member(document, "parameters");
    if (!parameters.is_object())
        fail("letter template 'parameters' must be a JSON object");

    for (const auto &item : parameters.items()) {
        const nlohmann::json &value = item.value();
        if (!value.is_boolean() && !value.is_number() && !value.is_string())
            fail("letter template parameter '" + item.key() +
                 "' must be a boolean, a number or a string; nested values are not part of the contract");
        result.parameters.emplace(item.key(), value);
    }

    if (options.schema != nullptr)
        validate_parameters(result.parameters, *options.schema);

    return result;
}

void LetterTemplate::save(const std::string &path) const
{
    std::ofstream stream(path, std::ios::binary | std::ios::trunc);
    if (!stream)
        fail("cannot open letter template '" + path + "' for writing");
    stream << to_json().dump(2) << '\n';
    if (!stream)
        fail("cannot write letter template '" + path + "'");
}

LetterTemplate LetterTemplate::load(const std::string &path, const LoadOptions &options)
{
    std::ifstream stream(path, std::ios::binary);
    if (!stream)
        fail("cannot open letter template '" + path + "' for reading");

    nlohmann::json document;
    try {
        document = nlohmann::json::parse(stream);
    } catch (const nlohmann::json::exception &error) {
        fail("letter template '" + path + "' is not valid JSON: " + error.what());
    }
    return from_json(document, options);
}

void validate_parameters(const Parameters &parameters, const Schema &schema)
{
    for (const auto &entry : parameters) {
        const auto spec_it = schema.find(entry.first);
        if (spec_it == schema.end())
            continue; // Unknown IDs are preserved, never coerced or dropped.

        const FieldSpec     &spec  = spec_it->second;
        const nlohmann::json &value = entry.second;
        const auto reject = [&](const std::string &why) {
            fail("parameter '" + entry.first + "': " + why);
        };

        switch (spec.kind) {
        case ValueKind::Boolean:
            if (!value.is_boolean())
                reject("expected a boolean");
            break;
        case ValueKind::Integer:
            if (!value.is_number_integer() && !value.is_number_unsigned())
                reject("expected an integer");
            break;
        case ValueKind::Number:
            if (!value.is_number())
                reject("expected a number");
            break;
        case ValueKind::Enum: {
            if (!value.is_string())
                reject("expected one of the declared enum names");
            const std::string name = value.get<std::string>();
            if (std::find(spec.enum_values.begin(), spec.enum_values.end(), name) == spec.enum_values.end())
                reject("unknown enum value '" + name + "'");
            break;
        }
        case ValueKind::Text:
            if (!value.is_string())
                reject("expected text");
            break;
        }

        if (spec.bounded && (spec.kind == ValueKind::Number || spec.kind == ValueKind::Integer)) {
            const double number = value.get<double>();
            if (number < spec.minimum || number > spec.maximum)
                reject("value " + number_to_text(number) + " is outside the established range [" +
                       number_to_text(spec.minimum) + ", " + number_to_text(spec.maximum) + "]");
        }
    }
}

} // namespace LetterMode
} // namespace Slic3r
