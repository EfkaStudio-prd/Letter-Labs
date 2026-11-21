#include <catch2/catch_test_macros.hpp>
#include <nlohmann/json.hpp>

#include "libslic3r/LetterMode/Template.hpp"

#include <filesystem>
#include <fstream>
#include <string>

using Slic3r::LetterMode::FieldSpec;
using Slic3r::LetterMode::LetterTemplate;
using Slic3r::LetterMode::LoadOptions;
using Slic3r::LetterMode::Parameters;
using Slic3r::LetterMode::Schema;
using Slic3r::LetterMode::TemplateError;
using Slic3r::LetterMode::ValueKind;

namespace {

LetterTemplate minimal_template()
{
    LetterTemplate letter;
    letter.machine_id = "iguana-800-1.2";
    letter.parameters = {{"letterShell.dbHeightShell", 42.123456789},
                         {"colorControl.dbLayerHeight[0]", 10.25},
                         {"footStep.bUsed[0]", false}};
    return letter;
}

Schema fixture_schema()
{
    Schema schema;

    FieldSpec height;
    height.kind    = ValueKind::Number;
    height.unit    = "mm";
    height.bounded = true;
    height.minimum = 0.1;
    height.maximum = 1000.0;
    schema.emplace("letterShell.dbHeightShell", height);

    FieldSpec layer;
    layer.kind = ValueKind::Number;
    layer.unit = "mm";
    schema.emplace("colorControl.dbLayerHeight[0]", layer);

    FieldSpec selection;
    selection.kind        = ValueKind::Enum;
    selection.enum_values = {"none", "straight", "bevel"};
    schema.emplace("letterShell.iSideLineSel", selection);

    FieldSpec used;
    used.kind = ValueKind::Boolean;
    schema.emplace("footStep.bUsed[0]", used);

    return schema;
}

} // namespace

TEST_CASE("Letter Mode template round-trips machine identity and original parameter IDs")
{
    const LetterTemplate source   = minimal_template();
    const LetterTemplate restored = LetterTemplate::from_json(source.to_json());

    REQUIRE(restored.machine_id == source.machine_id);
    REQUIRE(restored.parameters == source.parameters);
    REQUIRE(restored.parameters.at("letterShell.dbHeightShell").get<double>() == 42.123456789);
    REQUIRE(restored.parameters.count("colorControl.dbLayerHeight[0]") == 1);
    REQUIRE(restored.parameters.at("colorControl.dbLayerHeight[0]").get<double>() == 10.25);
    REQUIRE(restored.parameters.at("footStep.bUsed[0]").get<bool>() == false);
}

TEST_CASE("Letter Mode template preserves full numeric precision")
{
    const double precise = 42.123456789012345;
    LetterTemplate source;
    source.machine_id = "iguana-800-1.2";
    source.parameters = {{"letterShell.dbHeightShell", precise}};

    const LetterTemplate restored = LetterTemplate::from_json(source.to_json());
    REQUIRE(restored.parameters.at("letterShell.dbHeightShell").get<double>() == precise);
    REQUIRE(restored.parameters.at("letterShell.dbHeightShell").dump() ==
            source.parameters.at("letterShell.dbHeightShell").dump());
}

TEST_CASE("Letter Mode template rejects unsupported schema and missing machine identity")
{
    REQUIRE_THROWS_AS(LetterTemplate::from_json({{"schema", "unknown"}, {"version", 1}, {"machine_id", "machine"},
                                                 {"parameters", nlohmann::json::object()}}),
                      TemplateError);
    REQUIRE_THROWS_AS(LetterTemplate::from_json({{"schema", "efka.letter-mode-template"}, {"version", 1},
                                                 {"machine_id", ""}, {"parameters", nlohmann::json::object()}}),
                      TemplateError);
    REQUIRE_THROWS_AS(LetterTemplate::from_json({{"schema", "efka.letter-mode-template"}, {"version", 1},
                                                 {"parameters", nlohmann::json::object()}}),
                      TemplateError);
}

TEST_CASE("Letter Mode template refuses versions it cannot read")
{
    REQUIRE_THROWS_AS(LetterTemplate::from_json({{"schema", "efka.letter-mode-template"}, {"version", 2},
                                                 {"machine_id", "machine"}, {"parameters", nlohmann::json::object()}}),
                      TemplateError);
    REQUIRE_THROWS_AS(LetterTemplate::from_json({{"schema", "efka.letter-mode-template"}, {"version", "1"},
                                                 {"machine_id", "machine"}, {"parameters", nlohmann::json::object()}}),
                      TemplateError);
}

TEST_CASE("Letter Mode template round-trips through a file without loss")
{
    const LetterTemplate source = minimal_template();
    const auto           path   = std::filesystem::temp_directory_path() / "letter_mode_template_roundtrip.json";

    source.save(path.string());
    const LetterTemplate restored = LetterTemplate::load(path.string());
    std::filesystem::remove(path);

    REQUIRE(restored.machine_id == source.machine_id);
    REQUIRE(restored.parameters == source.parameters);
}

TEST_CASE("Letter Mode template pins machine and profile identity")
{
    LetterTemplate source = minimal_template();
    source.profile_id     = "Bambu Lab X1 Carbon 0.4";

    LoadOptions machine_pin;
    machine_pin.expected_machine_id = "some-other-machine";
    REQUIRE_THROWS_AS(LetterTemplate::from_json(source.to_json(), machine_pin), TemplateError);

    LoadOptions profile_pin;
    profile_pin.expected_profile_id = "Different profile";
    REQUIRE_THROWS_AS(LetterTemplate::from_json(source.to_json(), profile_pin), TemplateError);

    LoadOptions matching;
    matching.expected_machine_id = source.machine_id;
    matching.expected_profile_id = source.profile_id;
    REQUIRE_NOTHROW(LetterTemplate::from_json(source.to_json(), matching));
}

TEST_CASE("Letter Mode template validates declared units, enums and ranges")
{
    const Schema schema = fixture_schema();

    REQUIRE(schema.at("letterShell.dbHeightShell").unit == "mm");
    REQUIRE(schema.at("colorControl.dbLayerHeight[0]").unit == "mm");

    LetterTemplate valid;
    valid.machine_id = "iguana-800-1.2";
    valid.parameters = {{"letterShell.dbHeightShell", 25.0},
                        {"colorControl.dbLayerHeight[0]", 2.5},
                        {"letterShell.iSideLineSel", "bevel"},
                        {"footStep.bUsed[0]", true}};
    REQUIRE_NOTHROW(Slic3r::LetterMode::validate_parameters(valid.parameters, schema));

    LoadOptions options;
    options.schema = &schema;
    REQUIRE_NOTHROW(LetterTemplate::from_json(valid.to_json(), options));

    Parameters wrong_type = valid.parameters;
    wrong_type["footStep.bUsed[0]"] = "true";
    REQUIRE_THROWS_AS(Slic3r::LetterMode::validate_parameters(wrong_type, schema), TemplateError);

    Parameters unknown_enum = valid.parameters;
    unknown_enum["letterShell.iSideLineSel"] = "chamfer";
    REQUIRE_THROWS_AS(Slic3r::LetterMode::validate_parameters(unknown_enum, schema), TemplateError);

    Parameters out_of_range = valid.parameters;
    out_of_range["letterShell.dbHeightShell"] = 5000.0;
    REQUIRE_THROWS_AS(Slic3r::LetterMode::validate_parameters(out_of_range, schema), TemplateError);

    Parameters below_range = valid.parameters;
    below_range["letterShell.dbHeightShell"] = 0.0;
    REQUIRE_THROWS_AS(Slic3r::LetterMode::validate_parameters(below_range, schema), TemplateError);
}

TEST_CASE("Letter Mode template keeps parameters the schema does not know")
{
    Schema schema = fixture_schema();

    LetterTemplate source;
    source.machine_id = "iguana-800-1.2";
    source.parameters = {{"letterShell.dbHeightShell", 25.0},
                         {"connectWord.sVendorOnlyKey", "preserved"}};

    LoadOptions options;
    options.schema = &schema;
    const LetterTemplate restored = LetterTemplate::from_json(source.to_json(), options);

    REQUIRE(restored.parameters.at("connectWord.sVendorOnlyKey").get<std::string>() == "preserved");
}
