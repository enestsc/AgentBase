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
| 3 | Başlatılmamış projede anlaşılır hata | ✅ Tamamlandı | Dört komut grubunda init yönlendirmesi ve yan etkisizlik testi; harici plan doğrulaması bağımsız |
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
| 8 | Rol başına model/efor ayarı | ✅ Tamamlandı | Resmî şemalar ve modeller kontrol edildi; docs/provider-models.md; gerçek sağlayıcı oturumu doğrulanmadı |
| 9 | Bellek bakımı: `memory prune/supersede` komutları | ✅ Tamamlandı | Kimlikli seçim, gerekçe, dry-run, arşiv ve kanıt indeksi birlikte yazılır; elle yazılmış/kimliksiz eski notlar korunur |
| 10 | Rol/skill prompt kalitesi denetimi | ✅ Tamamlandı | docs/prompt-audit.md raporu ve önerilen diff önce kaydedildi; 16 rol/7 skill incelendi, düzeltmeler uygulandı; model oturumu denenmedi |
| 11 | Skill kataloğunu genişlet: release, changelog, PR özeti | ✅ Tamamlandı | Ön plan paylaşıldı; 3 skill ve rol yönlendirmeleri eklendi (toplam 10); yükseltme testi |
| 12 | Görev devrinde rol çıktısı şablonu (handoff alanlarını zorunlu doğrula) | Orta | `skills/agentbase-plan-tasks` yalnızca metinle istiyor, araç doğrulamıyor |
| — | Cowork / masaüstü otomasyonu | Kapsam dışı | AgentBase'in çekirdeğiyle ilgisiz |

Model/efor kaynağı: [resmî belgelerle kontrol edilen öneriler](docs/provider-models.md).
Önceki video özetindeki fiyat/model iddiaları doğrulanmış kaynak sayılmaz; önerilerden çıkarıldı.

## Bilinen sınırlar

- Alt ajan yürütme, izin ve sandbox sağlayıcı çalışma zamanındadır; AgentBase bunları denetlemez.
- "Görev sonunda kullanılan ajanı bildir" kuralı bir talimattır, araç zorlamaz.
