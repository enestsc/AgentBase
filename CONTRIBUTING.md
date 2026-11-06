# Contributing

## Geliştirme ortamı

Python 3.11+ gerekir. Çalışma zamanı bağımlılığı eklemeyin; yalnızca `dev` extra'sı geliştirme araçları içindir.

```bash
pip install -e ".[dev]"
ruff check src tests
python -m unittest discover -s tests
```

## Kurallar

- `main`'e doğrudan değil, ayrı dal + PR ile çalışın.
- Commit mesajlarına AI imzası / co-author satırı eklemeyin (bkz. `src/agentbase/assets/policy.md`).
- Güvenlik/dosya yazma kararlarında "neden"i anlatan kısa yorum ekleyin.
- Yeni davranış için test ekleyin; dosya yazan kod `fs.py` içindeki atomik/confined yardımcıları kullanmalı.

## Bilinen atlanan test

`tests/test_install.py` içindeki symlink testi, işletim sistemi symlink oluşturmaya izin vermezse atlanır
(Windows'ta Geliştirici Modu veya yönetici hakkı olmadan). Linux/macOS CI'da çalışır.
