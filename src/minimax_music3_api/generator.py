from pathlib import Path
import json
import threading

import numpy as np

from .config import Settings


class MusicGenerator:
    """Lazy-load the complete pipeline and serialize single-GPU inference."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pipeline = None
        self.load_lock = threading.Lock()
        self.generate_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.pipeline is not None

    def load(self) -> None:
        if self.loaded:
            return
        with self.load_lock:
            if self.loaded:
                return
            if not self.settings.model_path.exists():
                raise FileNotFoundError(f"Model path does not exist: {self.settings.model_path}")
            import torch
            from diffusers import ComponentsManager, ModularPipeline
            from diffusers.hooks import apply_group_offloading
            self._make_local_manifest()
            manager = ComponentsManager()
            if self.settings.cpu_offload:
                manager.enable_auto_cpu_offload(device=self.settings.device)
            pipe = ModularPipeline.from_pretrained(
                str(self.settings.model_path),
                components_manager=manager,
                local_files_only=True,
            )
            pipe.load_components(dtype=getattr(torch, self.settings.dtype), local_files_only=True)
            if self.settings.language_model_streaming:
                apply_group_offloading(pipe.language_model, onload_device=torch.device(self.settings.device), offload_type="leaf_level", use_stream=True)
            elif not self.settings.cpu_offload:
                pipe.to(self.settings.device)
            self.pipeline = pipe

    def _make_local_manifest(self) -> None:
        """Rewrite the downloaded manifest's HF component references to local paths."""
        manifest_path = self.settings.model_path / "modular_model_index.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        changed = False
        for value in manifest.values():
            if not isinstance(value, list) or len(value) < 3 or not isinstance(value[2], dict):
                continue
            options = value[2]
            if options.get("pretrained_model_name_or_path") != str(self.settings.model_path):
                options["pretrained_model_name_or_path"] = str(self.settings.model_path)
                changed = True
        if changed:
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def generate(self, lyrics: str, instructions: str, duration_seconds: float, seed: int, output_path: Path) -> Path:
        import soundfile as sf
        import torch
        self.load()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.generate_lock, torch.inference_mode():
            generator = torch.Generator(self.settings.device).manual_seed(seed)
            audio = self.pipeline(
                prompt=instructions,
                lyrics=lyrics,
                audio_duration=duration_seconds,
                generator=generator,
                output="audios",
            )[0]
            # Diffusers may return either a torch tensor or a NumPy array depending on
            # the pipeline/output configuration. Normalize both to soundfile's
            # (samples, channels) NumPy layout before writing the WAV.
            if isinstance(audio, torch.Tensor):
                samples = audio.T.float().cpu().numpy()
            else:
                samples = np.asarray(audio).T.astype("float32", copy=False)
            sf.write(output_path, samples, self.pipeline.sampling_rate, subtype="PCM_16")
        return output_path
