# AgentBase

[Yerel host test makbuzları](docs/guides/test-receipts.tr.md): açık argv/rıza,
kaynak/görev hash bağları ve stale kontrolü; host çalıştırması sandbox değildir.

Yeni yerel temeller: SHA'ya sabitlenmiş ve incelemeli GitHub skill kurulumu,
isteğe bağlı kullanım verisi içe alımı, yedi hazır paket, mevcut DAG'a şartname
derleme, çevrimdışı değerlendirme ve tekrar üretilebilir plugin paketleri.
Çoklu skill restore, stdin kullanım yakalama, artımlı görev uzlaştırma ve hash
tabanlı kod haritası eklendi. Açık izinli çevrimdışı Docker worker sınırlı öneriler
döndürür; bulut sağlayıcılar arası yürütme henüz desteklenmez.
Kimlik bilgisini worker'dan ayıran isteğe bağlı gateway sahte anahtarlı gerçek
Docker öz testi içerir; native ücretli çalıştırma adaptör entegrasyonunu bekler.
Dış ağı kapalı native smoke testleri, sentetik API yanıt çözümleme, Claude plugin
keşfi ve tek vakalı native regex eval akışını doğrular. Sonuçlar açıkça mock'tur;
gerçek model, kullanım veya kalite ölçümü sayılmaz.
[Türkçe rehber](docs/guides/foundations.tr.md) · [English guide](docs/guides/foundations.md) ·
[Güncel durum ve sınırlar](docs/development/STATUS.md).

Bu checkout artık kendi yönetilen kurulumunu, görev DAG'ını ve doğrulanmış
devirlerini geliştirmede kullanıyor. [Kendi projede kullanım ve devam rehberi](docs/guides/self-use.tr.md),
gerçek host delegasyonu ile üretilmiş native tanımların keşfini ayrı açıklar.

```bash
agentbase init --provider both --pack python --pack security --dry-run
agentbase skills add https://github.com/owner/repository --path skills/example
agentbase usage configure --source codex-exec-v1
agentbase usage --week --json
agentbase spec reconcile health
agentbase explain --write --feature authentication
agentbase local models --consent
agentbase eval capabilities --provider claude --consent
```

Skill ekleme/güncelleme önce plan üretir; uygulama tam `--plan-id` ve yüksek
önemli bulgular için ayrı `--acknowledge` ister. Kullanım kaynak bazında açık
onayla yerel tutulur; bilinmeyen metrikler null kalır. Betik çalıştırma, bağımlılık
kurma, analitik yükleme, ücretli model testi veya yayınlama otomatik yapılmaz.
GitHub işlemleri açık ağ erişimi kullanır; normal proje kurulumu çevrimdışıdır.
[Güven modeli](docs/security/trust-model.md) · [Mimari](docs/architecture/overview.md).

**OpenAI Codex** ve **Claude Code** için sağlayıcıya özgü (native) yapay zekâ geliştirme iş akışları.
Tek kaynaklı roller, skill'ler ve politika; üretilen native adaptörler; deterministik koordinasyon
için bağımlılıksız küçük bir Python CLI. İngilizce: [README.md](README.md).

AgentBase bir çıkarım (inference) çerçevesi değildir; mevcut ajan çalışma zamanlarını kullanır.

## Kurulum

Python 3.11+ gerekir. Çalışma zamanı bağımlılığı yoktur.

```bash
pip install git+https://github.com/enestsc/AgentBase.git
cd projeniz
agentbase init --provider both      # codex | claude | both
agentbase doctor
```

`init --dry-run` tüm değişiklikleri önceden gösterir. Mevcut `AGENTS.md` / `CLAUDE.md` içeriği
bayt bayt korunur; AgentBase yalnızca işaretli bir bloğa sahiptir. CLI'yi yükselttikten sonra
`agentbase update` çalıştırın; yerel olarak düzenlenmiş yönetilen dosyalar ezilmez.

## Kurulan dosyalar

| Yol | Amaç |
|---|---|
| `AGENTS.md`, `CLAUDE.md` (işaretli blok) | Ortak talimatlar |
| `.codex/agents/agentbase-*.toml` | Codex özel ajanları |
| `.claude/agents/agentbase-*.md` | Claude Code alt ajanları |
| `.agents/skills/…`, `.claude/skills/…` | Kademeli yüklenen skill'ler |
| `.agentbase/` | Politika, roller, ayarlar, görev DAG'ı, bellek, manifest |

## Komutlar

Proje üzerinde `explain`, `context`, `memory` ve `tasks` için önce `agentbase init`
gerekir; eksikse anlaşılır hata verilir. `tasks validate --file` bağımsız çalışır.

```text
agentbase roles | skills            rolleri / skill'leri listeler
agentbase uninstall [--dry-run] [--purge]   yönetilen dosya/blokları kaldırır; --purge .agentbase durumunu da siler
agentbase configure --mode sequential|safe-parallel
agentbase context ...              bütçeli dosya getirme (tahmini boyut)
agentbase explain [--write]        kanıta dayalı yapı haritası (model çağrısı yok)
agentbase tasks ...                görev DAG'ını doğrula / planla / durum geçişi
agentbase tasks validate-handoff --file handoff.json   devir alanlarını ve yazma kapsamını doğrula
agentbase tasks test TASK_ID --source src --consent --argv MUTLAK_EXE ARGLAR   güvenilen host kontrolü; sandbox değil
agentbase tasks receipt RECEIPT_ID   yerel kaynak/görev güncelliği; bağımsız kanıt değil
agentbase memory ...               kanıtlı notlar, senkronizasyon, devir teslim
agentbase memory list              kimlikleri ve düzenleme çakışmalarını gösterir
agentbase memory prune --id ID --reason "çözüldü" --dry-run
agentbase memory supersede --id ID --reason "değişti" --text "yeni not" --evidence src/app.py:1 --dry-run
agentbase local ...                isteğe bağlı yerel Ollama önerileri (dosya değiştirmez)
```

## Örnek oturum

```bash
agentbase init --provider both --dry-run   # önizleme, hiçbir şey yazmaz
agentbase init --provider both
agentbase doctor                           # çevrimdışı tanılama
agentbase tasks import --file examples/tasks.example.json
agentbase tasks ready                      # şimdi başlayabilecek görevler (işçi başlatmaz)
agentbase tasks transition api-design ready
agentbase tasks transition api-design running
agentbase tasks validate-handoff --file handoff.json  # gerçek gözlemlerle hazırla; examples/handoff.example.json
agentbase tasks transition api-design review --handoff-file handoff.json
agentbase tasks transition api-design completed --evidence "docs/health-contract.md kabul edildi"
agentbase memory handoff                   # kısa, kanıtlı devir teslim
agentbase uninstall --dry-run              # temiz kaldırma önizlemesi
```

`tasks.example.json` test paketinde doğrulanır; şemayla her zaman uyumludur. Ana ajan her görev
sonunda hangi rolün/ajanın ne yaptığını (veya neden kullanılmadığını) bildirir.

Bellek bakımı yalnızca açıkça seçilen, değiştirilmemiş kimlikli notları işler; eski metni
ve kanıtını arşivler. Önizlemeyi inceledikten sonra `--dry-run` kaldırılır. Elle yazılmış
ve kimliksiz eski notlar korunur. Arşivler aktif bellek bütçesine girmez, diskte kalır.
Kanıt indeksi yeni not veya bakım yazımında v2'ye yükselir.

`handoff.json`, [örnekten](examples/handoff.example.json) gerçek gözlemlerle hazırlanır.
[Devir şeması](docs/handoffs.md): review için devir; tamamlanma için başarılı gözlem,
çözülmemiş hata olmaması ve verification kanıtı gerekir. Araç kimlik/alan/kapsam/bütçeyi
doğrular, kontrolleri çalıştırmaz. Yeniden çalışma eski devri geçersiz kılar;
devirsiz eski completed görevler okunur ama uyarıyla gösterilir.

## Kim neyi zorlar?

Roller sağlayıcıya göre model/efor önerisi içerir: basit okuyucular Luna/Haiku +
low, mimar/güvenlik Sol/Opus + high. [Alanlar ve kaynaklar](docs/provider-models.md).
[Prompt denetimi ve önerilen diff](docs/prompt-audit.md), sahiplik/salt okuma
sınırlarını ve yedi skill'in tetikleyici düzeltmelerini açıklar; gerçek model oturumu denenmedi.

Katalog artık 10 skill içerir. Yeni `agentbase-prepare-release`, `agentbase-changelog`
ve `agentbase-pr-summary`, sürüm hazırlığı, değişiklik notu ve PR taslağı üretir;
uzak yayınlama için yetki gerekir. Mevcut projede önce `agentbase update --dry-run`,
incelemeden sonra `agentbase update` çalıştırılır.

1. **AgentBase aracı (deterministik):** DAG doğrulama, geçiş kuralları, dosya sahiplik çakışmaları,
   yol kısıtlama, hash takipli dosyalar, atomik yazma, bağlam bütçeleri.
2. **Ana ajan politikası (yalnızca talimat):** ne zaman devredileceği, kapsam disiplini, otomatik
   commit/yapay zekâ imzası yok.
3. **Sağlayıcı çalışma zamanı:** gerçek alt ajan yürütme, sandbox ve izinler. AgentBase bunları
   kontrol ettiğini iddia etmez.

Varsayılan yürütme sıralıdır (eşzamanlılık 1). `safe-parallel` isteğe bağlıdır; yalnızca uyumlu
okuyucuları paralel çalıştırır, yazıcılar sıraya alınır.

Lisans: MIT.
