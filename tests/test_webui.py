from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEBUI = ROOT / "src" / "vampip" / "webui"


class WorkspaceWebUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (WEBUI / "index.html").read_text(encoding="utf-8")
        cls.javascript = (WEBUI / "app.js").read_text(encoding="utf-8")
        cls.styles = (WEBUI / "styles.css").read_text(encoding="utf-8")

    def test_workspace_is_a_top_level_asset_browser(self) -> None:
        self.assertIn('data-view="workspace"', self.html)
        self.assertNotIn('data-view="person"', self.html)
        self.assertIn('id="asset-workspace"', self.html)
        self.assertIn('id="asset-category-list"', self.html)
        self.assertIn("scenes, atoms, plugins, clothing, and Person presets", self.html)

    def test_person_controls_are_contextual(self) -> None:
        self.assertIn('id="person-context"', self.html)
        self.assertIn('id="person-target"', self.html)
        self.assertIn('id="select-person-button"', self.html)
        self.assertIn('id="add-person-button"', self.html)
        self.assertIn('id="atom-context"', self.html)
        self.assertIn('id="atom-target"', self.html)
        self.assertIn('id="select-atom-button"', self.html)
        self.assertIn('category.targetKind !== "person"', self.javascript)
        self.assertIn('api("/api/vam/person/add"', self.javascript)
        self.assertIn('api("/api/vam/person/select"', self.javascript)
        self.assertIn('api("/api/vam/atom/select"', self.javascript)
        self.assertNotIn("VaM will add and select", self.javascript)

    def test_workspace_uses_canonical_browse_and_apply_contracts(self) -> None:
        self.assertIn('api("/api/workspace/categories")', self.javascript)
        self.assertIn('api("/api/vam/scene")', self.javascript)
        self.assertIn('params.set("category", category.id)', self.javascript)
        self.assertIn('params.append("type", resourceType)', self.javascript)
        self.assertIn('api("/api/vam/resource/apply"', self.javascript)
        self.assertIn("requireBridgeQueue(result", self.javascript)
        self.assertIn("result.bridge_busy !== true", self.javascript)
        self.assertIn("Required packages remain enabled", self.javascript)
        self.assertNotIn('params.set("type", "Preset Hair")', self.javascript)
        self.assertNotIn('api("/api/vam/person/apply"', self.javascript)

    def test_scene_replace_requires_explicit_confirmation(self) -> None:
        self.assertIn("Replace current scene", self.javascript)
        self.assertIn("body.confirm_replace = true", self.javascript)
        self.assertIn("confirmSceneLoad(item, merge)", self.javascript)
        self.assertIn("merge,", self.javascript)
        self.assertIn("confirmRiskyAssetLoad(item, category)", self.javascript)
        self.assertIn("confirm_critical: confirmedRisk", self.javascript)

    def test_fallback_covers_broad_asset_families(self) -> None:
        for resource_type in (
            "Scene",
            "SubScenes",
            "Preset Atom",
            "Custom Unity Assets",
            "Plugins",
            "Clothing (Female)",
            "Clothing (Male)",
            "Preset Appearance",
            "Preset Clothing",
            "Preset Hair",
            "Preset Morphs",
            "Preset Pose",
            "Preset Skin",
        ):
            with self.subTest(resource_type=resource_type):
                self.assertIn(f'"{resource_type}"', self.javascript)

        self.assertIn('"apply-person-preset"', self.javascript)
        self.assertIn('"person-preset-hair"', self.javascript)
        self.assertIn('"person-preset-plugins"', self.javascript)

    def test_workspace_has_responsive_category_and_context_styles(self) -> None:
        for selector in (
            ".asset-workspace",
            ".asset-category-list",
            ".asset-category-button.is-active",
            ".asset-category-panel",
            ".asset-apply-mode",
            ".person-context",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.styles)


if __name__ == "__main__":
    unittest.main()
