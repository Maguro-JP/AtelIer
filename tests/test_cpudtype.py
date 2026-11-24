"""bf16 の命令の無い CPU で、描く本体を float32 に替える試験（engine.cpu_upcast）。

Actions の 16GB の機械で、bf16 の命令の無い CPU に当たった回だけ SDXL の 1 歩が約 36 分になった。
偽の機械（RAM の量と bf16 の速さを差し替える）と、小さな本物の部品（torch の Conv2d）で、
足りる機械では本体と VAE が float32 になり、bf16 で入ってきた値でも描けること、bf16 の速い CPU と RAM の足りない機械では替えないことを見る。
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atelier.ai import engine  # noqa: E402

try:
    import torch
except ImportError:   # 描く部品の無い機械
    torch = None


class FakeVAE(torch.nn.Module if torch is not None else object):
    """diffusers の AutoencoderKL の形だけをまねる。
    encode/decode は forward を通らず encoder/decoder を直接呼ぶ。"""

    def __init__(self):
        super().__init__()
        self.encoder = torch.nn.Conv2d(3, 4, 1)
        self.decoder = torch.nn.Conv2d(4, 3, 1)

    def encode(self, x):
        return self.encoder(x)

    def decode(self, z):
        return self.decoder(z)


@unittest.skipIf(torch is None, "torch がありません")
class CpuUpcastTest(unittest.TestCase):
    def pipe(self):
        class Pipe:
            pass
        p = Pipe()
        p.unet = torch.nn.Conv2d(4, 4, 3, padding=1).to(torch.bfloat16)
        p.vae = torch.nn.Conv2d(4, 3, 1).to(torch.bfloat16)
        p.text_encoder = torch.nn.Linear(8, 8).to(torch.bfloat16)
        return p

    def test_fits_on_16gb_for_sdxl(self):
        with mock.patch.object(engine, "total_ram_gb", return_value=16.7):   # Actions の ubuntu-latest
            self.assertTrue(engine.cpu_upcast_fits(6.9))
        with mock.patch.object(engine, "total_ram_gb", return_value=8.0):
            self.assertFalse(engine.cpu_upcast_fits(6.9))
        with mock.patch.object(engine, "total_ram_gb", return_value=16.7):   # 24GB 級の模型は入らない
            self.assertFalse(engine.cpu_upcast_fits(24.0))

    def test_slow_bf16_cpu_upcasts_denoiser_only(self):
        p, said = self.pipe(), []
        with mock.patch.object(engine, "bf16_fast", return_value=False), \
                mock.patch.object(torch.cuda, "is_available", return_value=False):
            self.assertTrue(engine.cpu_upcast(p, said.append))
        self.assertEqual(p.unet.weight.dtype, torch.float32)
        self.assertEqual(p.vae.weight.dtype, torch.float32)
        self.assertEqual(p.text_encoder.weight.dtype, torch.bfloat16)   # 文字の部品は bf16 のまま
        self.assertTrue(said and "float32" in said[0])   # 進みの欄に、どの形で描くかを出す
        out = p.unet(torch.randn(1, 4, 8, 8, dtype=torch.bfloat16))   # bf16 の値が入っても落ちない
        self.assertEqual(out.dtype, torch.float32)

    def test_slow_bf16_cpu_upcasts_vae_encode_and_decode(self):
        """VAE の encode/decode に bf16 の絵が入っても落ちない。
        Actions で、cpu_upcast で VAE を float32 にしたあと、アタリの描き重ね（img2img）で
        VAE の encode に bf16 の絵が入り、conv_in で
        RuntimeError: Input type (BFloat16) and bias type (float) should be the same
        となって落ちた。encode/decode は forward を通らないので、VAE 本体の入口だけでは
        bf16 がそのまま入る。入口の部品（encoder/decoder）にも同じ仕掛けを付ける。"""
        p, said = self.pipe(), []
        p.vae = FakeVAE().to(torch.bfloat16)   # diffusers の VAE の形をまねる
        with mock.patch.object(engine, "bf16_fast", return_value=False), \
                mock.patch.object(torch.cuda, "is_available", return_value=False):
            self.assertTrue(engine.cpu_upcast(p, said.append))
        self.assertEqual(p.vae.encoder.weight.dtype, torch.float32)
        self.assertEqual(p.vae.decoder.weight.dtype, torch.float32)
        # bf16 の絵を encode しても落ちない（直し前は RuntimeError）
        out = p.vae.encode(torch.randn(1, 3, 8, 8, dtype=torch.bfloat16))
        self.assertEqual(out.dtype, torch.float32)
        # decode も同じ
        out = p.vae.decode(torch.randn(1, 4, 8, 8, dtype=torch.bfloat16))
        self.assertEqual(out.dtype, torch.float32)

    def test_fast_bf16_cpu_keeps_bf16(self):
        p = self.pipe()
        with mock.patch.object(engine, "bf16_fast", return_value=True), \
                mock.patch.object(torch.cuda, "is_available", return_value=False):
            self.assertFalse(engine.cpu_upcast(p))
        self.assertEqual(p.unet.weight.dtype, torch.bfloat16)


if __name__ == "__main__":
    unittest.main()
