# Changelog

[Keep a Changelog](https://keepachangelog.com/) biçimi, [SemVer](https://semver.org/) sürümleme.

## [Unreleased]

### Docs
- 16 rol ve 7 skill için önce rapor/önerilen diff, ardından sahiplik, tetikleyici ve kanıt dili düzeltmeleri.
- `ROADMAP.md`: tamamlanan aşamalar ve kalan işlerin güncel durumu.

### Fixed
- Reject Windows executable aliases resolving to batch/script targets before host test launch; no-launch regression covers both `.cmd` and `.bat` without symlink privileges.
- Gateway request/tool field allowlists now reject remote MCP/container/context configuration, unknown top-level fields and stored item references before transport. Native synthetic compatibility remains verified; paid launch remains disabled.
- Başlatılmamış projede explain/context/memory/tasks artık önce `agentbase init` ister; yan etki oluşturmaz.
- `local`: `http://127.0.0.1:0` artık sessizce 11434'e düşmüyor, reddediliyor; HTTP hata yanıtı kapatılıyor (ResourceWarning).

### Added
- Explicit trusted host test receipts bound to canonical task/resource definitions, selected source inventories and executable hashes; bounded hash-only output/argv and stale reporting. Local records are unauthenticated and never automatically complete tasks or upgrade specification evidence. See the English/Turkish test-receipt guides.
- Local development self-use with a managed installation, preserved artifact inventory, real DAG transitions, independent helper handoffs and bilingual resume guide. Generated native definitions do not imply runtime activation.
- Network-disabled native image contract probes and fixed synthetic Responses/Messages smoke checks; canonical Claude plugin discovery and one-case native regex eval with explicit mock evidence, no keys/provider calls or imported code. Bounded client tool namespaces and the exact Claude beta query reuse the fixed gateway routes.
- Optional credential-isolating gateway with fixed official routes/models, stdin-only key bootstrap, internal worker network, bounded protocol, synthetic Docker self-test and expiry cleanup. No native paid launch is enabled.
- Transactional multi-skill restore, optional safe PyYAML syntax, offline curated discovery and non-executing dependency checks.
- Opt-in stdin usage capture, explicit cross-day uncertainty, incremental specification reconciliation and hash-bound reported test mappings.
- Incremental structural index, nested symbols/call candidates and targeted feature maps; Ollama installed-model preflight and structured proposals.
- Explicit native capability/static-validator probes and offline Docker TaskRunner with bounded snapshots, verified restrictions, timeout cleanup and untrusted proposals. Cloud execution stays disabled.
- Reviewed GitHub skill registry: immutable commit pins, bounded ZIP inspection, deterministic security/license findings, exact-plan apply, per-file hashes, update/rollback/export/one-skill restore, safe removal and provenance audit.
- Opt-in local usage capture adapters for documented Codex/Claude messages, unknown-value handling, deduplication, context/counter separation, reports, retention, deletion and JSON/CSV export.
- Seven curated canonical packs, custom selection registration, selective `init --pack`, recommendations and safe pack changes; legacy initialization preserved.
- Explicit Markdown specification-to-existing-DAG compilation and traceability; offline static evaluation and supplied-observation grading.
- Reproducible optional Claude/Codex plugin artifacts, duplicate-free `init/update --discovery plugin`, static integrity validation, isolated installed-wheel smoke, separate opt-in live GitHub smoke, architecture/security/reference decisions and bilingual guides.
- `tasks validate-handoff --file` ve `transition --handoff-file`: zorunlu devir alanları, görev kimliği/kapsam/bütçe kontrolü; review/tamamlanma kapısı ve yeniden çalışmada eski devrin iptali. Tarihî devirsiz tamamlanmalar uyarıyla okunur.
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
