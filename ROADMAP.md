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

## Bilinen sınırlar

- Alt ajan yürütme, izin ve sandbox sağlayıcı çalışma zamanındadır; AgentBase bunları denetlemez.
- "Görev sonunda kullanılan ajanı bildir" kuralı bir talimattır, araç zorlamaz.
