# Yol haritası ve ilerleme

Son güncelleme: 2026-11-14 · Dal: `chore/p1-hygiene` · Sürüm: 0.1.0 (Alpha)

Yeni temel modüllerin güncel durumu ve gerçek test sonuçları:
[STATUS](docs/development/STATUS.md), [devam planı](docs/development/ROADMAP.md),
[oturum devri](docs/development/HANDOFF.md). Aşağıdaki tarihî ilerleme korunmuştur.
Bu checkout'ta korunmuş gerçek AgentBase kurulumu, görev DAG'ı ve bağımsız yardımcı
ajan devirleri artık kullanıldı. Yardımcının saptadığı gateway uzak alan geçişi
açık izin listeleriyle kapatıldı. [Kendi projede kullanım](docs/guides/self-use.tr.md).
Yerel host test makbuzları artık açık argv/rıza, seçilen kaynak/görev/executable
hash bağları ve stale raporuyla mevcut DAG'a eklendi. Bunlar bağımsız veya
kriptografik doğrulanmış kanıt değildir. [Rehber](docs/guides/test-receipts.tr.md).
Güncel test ve paket sonuçları STATUS'tadır; eski tarihî sonuçlar aşağıda korunur.
Son eklenenler: dış ağı kapalı native image sözleşme/sentetik API testleri,
Claude kanonik plugin keşfi ve tek vakalı native regex eval. Gerçek sağlayıcı
çağrısı, ücretli çalıştırma ve model kalite ölçümü yapılmadı.

## Tamamlananlar

| Aşama | İçerik | Durum |
|---|---|---|
| P1 | `dev` bağımlılıkları, ruff, CI lint işi, CHANGELOG / CONTRIBUTING / SECURITY | ✅ |
| P2 | `cli`, `explain`, `local` testleri; 43 → 76 test; port 0 ve HTTPError düzeltmeleri | ✅ |
| P3 | CI'da paket derleme + `twine check`; `v*` etiketli release iş akışı | ✅ (PyPI yayını yapılmadı) |
| P4 | `agentbase uninstall [--dry-run] [--purge]`, `examples/tasks.example.json`, README örnek oturum (EN/TR) | ✅ |

Yerel doğrulama (2026-11-10): Windows / Python 3.14.4 üzerinde 101 test çalıştı,
100 başarılı, 1 atlandı (symlink izni yok); `python -m ruff check src tests` temiz.
Linux/macOS CI, Python 3.11 ve gerçek sağlayıcı ajan oturumları bu çalışmada denenmedi.
Skill Creator `quick_validate.py`, ortamda `yaml` bulunmadığı için çalışmadı;
bağımlılık kurulmadı. Katalog/üretim/yükseltme kontrolleri unittest ile yapıldı.

## Kalan işler

| # | İş | Durum | Not |
|---|---|---|---|
| 1 | Dalı GitHub'a gönderip PR aç | ✅ Tamamlandı | Kullanıcı onayıyla dal gönderildi; [PR #1](https://github.com/enestsc/AgentBase/pull/1) açıldı (hedef main); birleştirme kullanıcıda; Linux/macOS CI sonucu henüz doğrulanmadı |
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
| 12 | Görev devrinde rol çıktısı şablonu | ✅ Tamamlandı | Ön plan paylaşıldı; JSON doğrulama, review/tamamlanma kapısı, kapsam/bütçe kontrolü ve eski devrin iptali; tarihî devirsiz tamamlanmalar uyarılır |
| — | Cowork / masaüstü otomasyonu | Kapsam dışı | AgentBase'in çekirdeğiyle ilgisiz |

Model/efor kaynağı: [resmî belgelerle kontrol edilen öneriler](docs/provider-models.md).
Önceki video özetindeki fiyat/model iddiaları doğrulanmış kaynak sayılmaz; önerilerden çıkarıldı.

## Bilinen sınırlar

- Alt ajan yürütme, izin ve sandbox sağlayıcı çalışma zamanındadır; AgentBase bunları denetlemez.
- "Görev sonunda kullanılan ajanı bildir" kuralı bir talimattır, araç zorlamaz.
