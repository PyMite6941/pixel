import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.registry import ModelRegistry, ModelImage, get_catalog, find_in_catalog


class TestModelRegistry:
    def test_list_images_empty(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        assert reg.list_images() == []

    def test_add_local_file(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        model_file = tmp_path / "test.gguf"
        model_file.write_bytes(b"\x00\x01\x02" * 1000)

        img = reg.add_local_file(model_file, "test_model", description="A test GGUF", tags=["test"])
        assert img.name == "test_model"
        assert img.source_type == "gguf_file"
        assert img.size_bytes == 3000
        assert "A test GGUF" in img.description
        assert img.provider_name == "test_model"

        reg2 = ModelRegistry(images_dir=tmp_path / "imgs")
        assert len(reg2.list_images()) == 1
        assert reg2.get_image("test_model") is not None

    def test_remove_image(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        model_file = tmp_path / "remove.gguf"
        model_file.write_bytes(b"\x00" * 100)
        reg.add_local_file(model_file, "remove_me")

        assert reg.remove_image("remove_me") is True
        assert reg.get_image("remove_me") is None
        assert not model_file.exists()

    def test_remove_nonexistent(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        assert reg.remove_image("nope") is False

    def test_register_ollama_model(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        img = reg.register_ollama_model("llama3.2", tags=["local", "ollama"])
        assert img.name == "llama3.2"
        assert img.source_type == "ollama"
        assert img.provider_name == "ollama"

        img2 = reg.register_ollama_model("llama3.2")
        assert img2 == img

    def test_get_by_provider(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        f1 = tmp_path / "a.gguf"
        f2 = tmp_path / "b.gguf"
        f1.write_bytes(b"\x01" * 100)
        f2.write_bytes(b"\x02" * 100)
        reg.add_local_file(f1, "model_a")
        reg.add_local_file(f2, "model_b")

        imgs = reg.get_by_provider("model_a")
        assert len(imgs) == 1
        assert imgs[0].name == "model_a"

    def test_total_size(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        f1 = tmp_path / "m1.gguf"
        f2 = tmp_path / "m2.gguf"
        f1.write_bytes(b"\x01" * 500)
        f2.write_bytes(b"\x02" * 1500)
        reg.add_local_file(f1, "m1")
        reg.add_local_file(f2, "m2")
        assert reg.total_size_bytes() == 2000

    def test_total_size_str(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        f = tmp_path / "big.gguf"
        f.write_bytes(b"\x00" * 2048)
        reg.add_local_file(f, "big")
        size_str = reg.total_size_str()
        assert "KB" in size_str or "bytes" in size_str

    def test_add_nonexistent_file(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        try:
            reg.add_local_file(tmp_path / "nope.gguf", "fail")
            assert False, "Should have raised"
        except FileNotFoundError:
            pass

    def test_model_image_dataclass(self):
        img = ModelImage(name="test", source_type="gguf_file", path="/tmp/test.gguf",
                         size_bytes=1000, loaded=False, tags=["test"])
        assert img.name == "test"
        assert img.provider_name == ""

    def test_pull_from_url_invalid(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        try:
            reg.pull_from_url("https://invalid.url/nope.gguf", name="fail")
            assert False, "Should have raised"
        except Exception:
            pass

    def test_pull_from_url_cached_file(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        content = b"\xaa" * 200
        dest = reg.images_dir / "cached.gguf"
        dest.write_bytes(content)
        img = reg.pull_from_url("https://example.com/cached.gguf", name="cached")
        assert img.size_bytes == 200
        assert img.source_type == "url"

    def test_pull_from_ollama_via_registry(self, tmp_path: Path):
        reg = ModelRegistry(images_dir=tmp_path / "imgs")
        img = reg.register_ollama_model("llama3.2")
        assert img.source_type == "ollama"
        assert img.provider_name == "ollama"

    def test_get_catalog(self):
        catalog = get_catalog()
        assert len(catalog) >= 1
        names = [e["name"] for e in catalog]
        assert "llama3.2-3b" in names

    def test_find_in_catalog_by_name(self):
        entry = find_in_catalog("phi3.5-mini")
        assert entry is not None
        assert entry["name"] == "phi3.5-mini"

    def test_find_in_catalog_by_tag(self):
        entry = find_in_catalog("coding")
        assert entry is not None
        assert "coding" in entry.get("tags", [])

    def test_find_in_catalog_nonexistent(self):
        entry = find_in_catalog("nonexistent_model_xyz")
        assert entry is None
