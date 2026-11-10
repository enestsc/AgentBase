# Yol haritası ve ilerleme

Son güncelleme: 2026-11-06 · Dal: `chore/p1-hygiene` · Sürüm: 0.1.0 (Alpha)

## Tamamlananlar

| Aşama | İçerik | Durum |
|---|---|---|
| P1 | `dev` bağımlılıkları, ruff, CI lint işi, CHANGELOG / CONTRIBUTING / SECURITY | ✅ |
| P2 | `cli`, `explain`, `local` testleri; 43 → 76 test; port 0 ve HTTPError düzeltmeleri | ✅ |
| P3 | CI'da paket derleme + `twine check`; `v*` etiketli release iş akışı | ✅ (PyPI yayını yapılmadı) |
| P4 | `agentbase uninstall [--dry-run] [--purge]`, `examples/tasks.example.json`, README örnek oturum (EN/TR) | ✅ |

Yerel doğrulama: `ruff check` temiz, 76 test geçti (1 atlandı: Windows'ta symlink izni yok).

## Kalan işler

| # | İş | Durum | Not |
|---|---|---|---|
| 1 | Dalı GitHub'a gönderip PR aç | ⏳ Bekliyor | CI Linux/macOS'ta henüz hiç çalışmadı |
| 2 | PyPI trusted publisher tanımla, `v*` etiketi at | ⏳ Bekliyor | Hesap işlemi kullanıcıda; tanımlanana kadar publish işi çalışmaz |
| 3 | Başlatılmamış projede `explain`/`context`/`memory`/`tasks` için anlaşılır hata ("önce `agentbase init`") | ⏳ Yapılacak | Şu an ham OS hatası dönüyor; test de eklenecek |
| 4 | Symlink testini Linux/macOS CI'da doğrula | ⏳ CI'a bağlı | Windows'ta atlanıyor |
| 5 | Yavaş testleri bul ve hızlandır | 💤 Düşük öncelik | Süit 8–27 sn arasında değişiyor |
| 6 | `docs/` altında baştan sona kullanım rehberi (TR/EN) | 💤 Düşük öncelik | README yalnızca komutları anlatıyor |
| 7 | Gerçek bir projede Codex/Claude Code ile uçtan uca deneme | ⏳ Doğrulanmadı | Araç mantığı test edildi; ajanların gerçekten rol seçimi yapması denenmedi |

## Yeni öneriler (2026-11-10, video notları + kod incelemesi)

Kaynak: "Bana 27 Dakika Verin, Size Claude'u Profesyonelce Kullanmayı Öğreteyim" videosu. Not: video içeriği
(transkript) araçla okunamadı; aşağıdaki video bağlantıları kullanıcının yapıştırdığı özetten alındı,
kod gözlemleri ise depodan doğrulandı.

| # | İş | Öncelik | Dayanak (kodda doğrulanan) |
|---|---|---|---|
| 8 | Rol başına model/efor ayarı: okuyucu roller ucuz+düşük efor, mimar/güvenlik yüksek efor | Yüksek | `adapters.py:26` tüm Claude ajanlarında `model: inherit`; Codex TOML'unda model/efor alanı yok |
| 9 | Bellek bakımı: `memory prune/supersede` komutları | Yüksek | `memory.py` bütçe dolunca "elle temizle" diyor, temizleme komutu yok |
| 10 | Rol/skill prompt kalitesi denetimi (eski kalıp, çelişki, belirsiz tetikleyici) | Orta | `roles.json` ve 7 skill hiç denetlenmedi |
| 11 | Skill kataloğunu genişlet: tekrarlanan işler için (release, changelog, PR özeti) | Orta | Mevcut 7 skill yalnızca planlama/bellek/doğrulama |
| 12 | Görev devrinde rol çıktısı şablonu (handoff alanlarını zorunlu doğrula) | Orta | `skills/agentbase-plan-tasks` yalnızca metinle istiyor, araç doğrulamıyor |
| — | Cowork / masaüstü otomasyonu | Kapsam dışı | AgentBase'in çekirdeğiyle ilgisiz |

Model/efor önerisi (geliştirme oturumları için): ana geliştirme Opus 5.5 + `high`; dosya yazma/geri alma gibi
güvenlik kritik tasarımlarda `xhigh`; test yazma ve rutin düzenlemelerde Sonnet 5.5 + `medium`; salt okuma
keşif alt ajanlarında Haiku 5.5 + `low`. Fable 5.2 yalnızca en zor tek seferlik işler için (fiyatı Opus 5.5'in 2 katı).

## Bilinen sınırlar

- Alt ajan yürütme, izin ve sandbox sağlayıcı çalışma zamanındadır; AgentBase bunları denetlemez.
- "Görev sonunda kullanılan ajanı bildir" kuralı bir talimattır, araç zorlamaz.
