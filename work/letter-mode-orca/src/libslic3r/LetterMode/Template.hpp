#pragma once

#include <map>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace Slic3r {
namespace LetterMode {

// Stable on-disk identity of a Letter Mode template. A template written by a
// different schema or a newer version must be rejected, never guessed at.
inline constexpr const char *TEMPLATE_SCHEMA  = "efka.letter-mode-template";
inline constexpr int         TEMPLATE_VERSION = 1;

class TemplateError : public std::runtime_error
{
public:
    using std::runtime_error::runtime_error;
};

// Value shape of a single original ZCCAD field. The kind is a UI/validation
// concern only; the template always stores the vendor value untouched.
enum class ValueKind {
    Boolean,
    Integer,
    Number,
    Enum,
    Text,
};

// Declared meaning of one original parameter ID. Units, bounds and enum labels
// are only filled in where the field inventory has evidence for them; an empty
// unit or unbounded spec means "not established", not "unitless".
struct FieldSpec
{
    ValueKind                kind = ValueKind::Number;
    std::string              unit;
    bool                     bounded = false;
    double                   minimum = 0.0;
    double                   maximum = 0.0;
    std::vector<std::string> enum_values;
};

using Schema     = std::map<std::string, FieldSpec>;
using Parameters = std::map<std::string, nlohmann::json>;

struct LoadOptions
{
    // Identity pins. Empty means "not pinned" and accepts whatever the file
    // declares; a non-empty value must match or loading fails.
    std::string expected_machine_id;
    std::string expected_profile_id;

    // Optional field metadata. When supplied, every parameter that the schema
    // knows is validated; parameters the schema does not know are preserved.
    const Schema *schema = nullptr;
};

class LetterTemplate
{
public:
    // Identity. machine_id is required and must never be empty.
    std::string machine_id;
    // Optional profile pin written into the template at save time.
    std::string profile_id;
    // Original ZCCAD parameter IDs, exactly as the vendor spells them, mapped
    // to their unmodified values.
    Parameters  parameters;

    nlohmann::json to_json() const;

    // Throws TemplateError for a wrong schema, an unsupported version, a
    // missing machine identity, a mismatched identity pin or an invalid value.
    static LetterTemplate from_json(const nlohmann::json &document, const LoadOptions &options = LoadOptions());

    void               save(const std::string &path) const;
    static LetterTemplate load(const std::string &path, const LoadOptions &options = LoadOptions());
};

// Throws TemplateError on the first value that contradicts its FieldSpec.
// Unknown IDs are ignored so vendor fields survive a schema that predates them.
void validate_parameters(const Parameters &parameters, const Schema &schema);

} // namespace LetterMode
} // namespace Slic3r
