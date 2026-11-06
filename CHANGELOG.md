# Changelog

[Keep a Changelog](https://keepachangelog.com/) biçimi, [SemVer](https://semver.org/) sürümleme.

## [Unreleased]

### Fixed
- `local`: `http://127.0.0.1:0` artık sessizce 11434'e düşmüyor, reddediliyor; HTTP hata yanıtı kapatılıyor (ResourceWarning).

### Added
- `cli`, `explain`, `local`, `uninstall` ve örnek plan için testler (43 → 76 test).
- `agentbase uninstall [--dry-run] [--purge]`: yalnızca manifestteki yönetilen öğeleri geri alır; kullanıcının `AGENTS.md`/`CLAUDE.md` içeriği birebir korunur, yerel düzenlenmiş yönetilen dosya varsa durur.
- CI'a paket derleme + `twine check` işi; `v*` etiketiyle tetiklenen PyPI release iş akışı (trusted publishing).
- Politika: görev sonunda hangi rolün/ajanın kullanıldığı bildirilir, belgeler aynı değişiklikte güncellenir (Codex ve Claude için ortak).
- Geliştirme bağımlılıkları (`dev` extra), ruff yapılandırması ve CI lint işi.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`.

## [0.1.0]

- İlk sürüm: Codex ve Claude Code için native adaptörler, görev DAG'ı, bütçeli bağlam, bellek ve isteğe bağlı yerel Ollama önerileri.
