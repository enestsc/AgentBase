# Changelog

[Keep a Changelog](https://keepachangelog.com/) biçimi, [SemVer](https://semver.org/) sürümleme.

## [Unreleased]

### Docs
- 16 rol ve 7 skill için önce rapor/önerilen diff, ardından sahiplik, tetikleyici ve kanıt dili düzeltmeleri.
- `ROADMAP.md`: tamamlanan aşamalar ve kalan işlerin güncel durumu.

### Fixed
- Başlatılmamış projede explain/context/memory/tasks artık önce `agentbase init` ister; yan etki oluşturmaz.
- `local`: `http://127.0.0.1:0` artık sessizce 11434'e düşmüyor, reddediliyor; HTTP hata yanıtı kapatılıyor (ResourceWarning).

### Added
- Release hazırlığı, changelog ve PR özeti için üç skill (toplam 10); mevcut kurulumdan güvenli yükseltme testi.
- `memory list/prune/supersede`: açık kimlik seçimi, gerekçe, dry-run, geri alınabilir arşiv ve tutarlı v2 kanıt indeksi; kullanıcı/kimliksiz eski notlar korunur.
- Rol başına doğrulanmış Codex model/efor ve Claude Code model/effort alanları; resmî kaynak notları.
- `cli`, `explain`, `local`, `uninstall` ve örnek plan için testler (43 → 76 test).
- `agentbase uninstall [--dry-run] [--purge]`: yalnızca manifestteki yönetilen öğeleri geri alır; kullanıcının `AGENTS.md`/`CLAUDE.md` içeriği birebir korunur, yerel düzenlenmiş yönetilen dosya varsa durur.
- CI'a paket derleme + `twine check` işi; `v*` etiketiyle tetiklenen PyPI release iş akışı (trusted publishing).
- Politika: görev sonunda hangi rolün/ajanın kullanıldığı bildirilir, belgeler aynı değişiklikte güncellenir (Codex ve Claude için ortak).
- Geliştirme bağımlılıkları (`dev` extra), ruff yapılandırması ve CI lint işi.
- `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`.

## [0.1.0]

- İlk sürüm: Codex ve Claude Code için native adaptörler, görev DAG'ı, bütçeli bağlam, bellek ve isteğe bağlı yerel Ollama önerileri.
