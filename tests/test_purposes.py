import pytest

from nala import purposes


def test_load_all_real_manifests_succeeds_with_correct_risk_profiles():
    manifests = purposes.load_all()

    assert set(manifests.keys()) == purposes.VALID_PURPOSE_NAMES
    assert manifests["projects"].risk_profile == "act_confirm"
    assert manifests["home"].risk_profile == "act_confirm"
    assert manifests["relationships"].risk_profile == "notify_only"
    assert manifests["baby"].risk_profile == "notify_only"
    assert manifests["finance"].risk_profile == "read_only"
    assert manifests["news"].risk_profile == "read_only"
    assert manifests["interests"].risk_profile == "read_only"
    assert manifests["purchase"].risk_profile == "read_only"


def test_risk_profile_for_unknown_purpose_returns_none():
    assert purposes.risk_profile_for("not_a_real_purpose") is None


def test_risk_profile_for_known_purpose():
    assert purposes.risk_profile_for("projects") == "act_confirm"


def test_missing_manifest_is_a_loud_failure(tmp_path):
    # Only create 7 of the 8 required purpose directories.
    for name in sorted(purposes.VALID_PURPOSE_NAMES)[:-1]:
        d = tmp_path / name
        d.mkdir()
        (d / "manifest.yaml").write_text(
            "display_name: X\nrisk_profile: read_only\nmemory_scope: x\ndefault_tier: cheap\n"
        )

    with pytest.raises(purposes.PurposeManifestError, match="missing manifest"):
        purposes.load_all(tmp_path)


def test_malformed_yaml_is_a_loud_failure(tmp_path):
    for name in purposes.VALID_PURPOSE_NAMES:
        d = tmp_path / name
        d.mkdir()
        (d / "manifest.yaml").write_text(
            "display_name: X\nrisk_profile: read_only\nmemory_scope: x\ndefault_tier: cheap\n"
        )
    # Corrupt one manifest with invalid YAML.
    broken = tmp_path / "projects" / "manifest.yaml"
    broken.write_text("display_name: [unterminated\n")

    with pytest.raises(purposes.PurposeManifestError, match="malformed YAML"):
        purposes.load_all(tmp_path)


def test_invalid_risk_profile_is_a_loud_failure(tmp_path):
    for name in purposes.VALID_PURPOSE_NAMES:
        d = tmp_path / name
        d.mkdir()
        (d / "manifest.yaml").write_text(
            "display_name: X\nrisk_profile: read_only\nmemory_scope: x\ndefault_tier: cheap\n"
        )
    bad = tmp_path / "home" / "manifest.yaml"
    bad.write_text("display_name: Home\nrisk_profile: yolo_mode\nmemory_scope: home\ndefault_tier: cheap\n")

    with pytest.raises(purposes.PurposeManifestError, match="invalid manifest"):
        purposes.load_all(tmp_path)


def test_manifest_missing_required_field_is_a_loud_failure(tmp_path):
    for name in purposes.VALID_PURPOSE_NAMES:
        d = tmp_path / name
        d.mkdir()
        (d / "manifest.yaml").write_text(
            "display_name: X\nrisk_profile: read_only\nmemory_scope: x\ndefault_tier: cheap\n"
        )
    incomplete = tmp_path / "finance" / "manifest.yaml"
    incomplete.write_text("display_name: Finance\nrisk_profile: read_only\n")  # missing memory_scope, default_tier

    with pytest.raises(purposes.PurposeManifestError, match="invalid manifest"):
        purposes.load_all(tmp_path)
