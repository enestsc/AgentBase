# AgentBase'i kendi geliştirmemizde kullanmak

Yetkili kaynak mevcut yerel checkout'tur. Koordinatör 2026-11-14'te `init
--provider both --dry-run` önizlemesini inceledikten sonra kanonik kurulumu burada
uyguladı. Yeni dal/worktree, commit, push, yayınlama, imported installer veya gerçek
sağlayıcı oturumu yok. AGENTS.md ve CLAUDE.md'nin özgün byte'ları dosya başlarında
korundu; kurulum sonlarına yönetilen blok ekledi.

Kurulum öncesi envanter, oturumun kendi bootstrap yardımcısı dahil 527 `.agentbase`
dosyasını kapsadı. Koordinatör ve bağımsız `dogfood_audit` yardımcısı SHA-256
değerlerini yeniden doğruladı. Derleme, şema, native image ve isteğe bağlı YAML
artefaktları korundu. `.agentbase` klasörünün varlığı proje kurulumu yapıldığını
göstermez; klasör silinebilir sayılmamalı. Özellikle `uninstall --purge`, buradaki
durum ve artefaktları siler.

Bu oturumda kullanılan gerçek akış:

| Görev | Gerçek yürütücü | Kapsam ve kanıt |
| --- | --- | --- |
| `selfuse-check` | `dogfood_audit` yardımcı ajanı, codebase-explorer rolü | Salt okuma; temiz doctor, değişikliksiz update, eşleşen 527 hash ve özgün talimat prefix'leri |
| `gateway-contract` | Ana koordinatör, backend-engineer rolü | Gateway ve regresyonlar; uzak MCP/container/bağlam ile bilinmeyen istek/araç alanlarının reddi |
| `boundary-review` | `boundary_audit` yardımcı ajanı, security-reviewer rolü | Salt okuma; bağımsız sanitizer matrisinde 29 red ve 6 desteklenen örnek |
| `verify-handoff` | Ana koordinatör, doğrulama/dokümantasyon rolleri | Tam unittest, Ruff, sentetik native uyumluluk, iki dilli belgeler ve kalıcı devir |

İki yardımcı ilk incelemeyi kurulumdan önce yaptı; o çalışma DAG üzerinden
yürütülmedi. Tablodaki kurulum sonrası kontroller ve yeniden inceleme, ilgili
görevler `running` olduktan sonra başlatıldı. Ortak dosya/durumun tek yazarı ana
koordinatördür. Mevcut görev motoruyla import, sync, running, review, devir
doğrulaması ve kanıtlı completion kullanıldı. Gateway görevinin kapsamına Python
test wrapper'ı, düzenlemeden önce proje kilidi altında ve plan doğrulanarak eklendi.
Varsayılan sequential/concurrency 1 korundu; ilk bağımsız host incelemeleri
AgentBase paralel zamanlayıcısının çalıştığı anlamına gelmez.

Her iki sağlayıcı için native rol/skill dosyaları üretildi. Bu açık oturum mevcut
host yardımcı ajan araçlarını kullandı; yeni native tanımların kendiliğinden
keşfedildiği/aktive olduğu varsayılmadı. Yerel skill'ler yönergedir; çalışma izni
ve yürütme kanıtı sağlamaz. Özgün CLAUDE.md zaten AGENTS.md'yi import ediyordu;
eklenen kanonik blok bu import'u tekrar içeriyor. Host'un bunu nasıl tekilleştirdiği
bu checkout'ta doğrulanmadı.

Bu depoda PowerShell ile devam:

```powershell
$env:PYTHONPATH='src'
python -m agentbase doctor
python -m agentbase update --dry-run
python -m agentbase tasks show
python -m agentbase tasks validate
python -m agentbase tasks ready
python -m agentbase memory handoff
```

Önce STATUS/HANDOFF ve görev kapsamlarını okuyun. Aktif durum `.agentbase/tasks.json`
içinde; envanter, özgün talimat kopyaları, devir JSON'ları ve mock raporları
`.agentbase/self-use-20261114/` altındadır. Bunlar ignored yerel durumdur;
commit edilmiş taşınabilir kanıt değildir. Dolu görev deposunun üzerine yeni plan
import etmeyin; yeni milestone için tamamlanan planı açıkça inceleyip arşivleyin.
Oturum bootstrap yardımcısını tekrar çalıştırmayın; kurulum zaten tamamlandı.

Yeni ve boş görev deposunda incelenmiş bir planın normal yaşam döngüsü:
`tasks validate --file reviewed-plan.json`, `tasks import --file reviewed-plan.json`,
`tasks sync`, `tasks transition ID running`, `tasks validate-handoff --file
handoff.json`, `tasks transition ID review --handoff-file handoff.json`, ardından
`tasks transition ID completed --evidence "Gözlenen kontrol ve artefakt"`.
Bildirdiğiniz kontrolleri gerçekten çalıştırın; CLI devirdeki komutları yürütmez.

Yeni güvenilen host kontrolleri için [test makbuzları](test-receipts.tr.md), açık
argv/rıza ve kaynak/görev/executable hash bağlarıyla stale raporu sağlar. Aynı
DAG kullanılır; otomatik tamamlanma veya bağımsız kimlik doğrulaması yoktur.
Bu devamda dört tamamlanmış görevin snapshot'ı
`.agentbase/receipt-check-20261114/prior-tasks.json` altında korunup proje kilidi
altında doğrulanmış takip görevleri eklendi; önceki durum değiştirilmedi.

Devir doğrulaması şema, kapsam ve kanıt kapılarını denetler. Bağımsız yardımcı
ajanın bildirdiği testler bile kimliği doğrulanmış yürütme makbuzu değildir.
Native mock testleri yalnız çözümleme/keşif/grading uyumluluğunu gösterir; gerçek
model davranışı, araç yürütmesi ve harcama doğrulanmadı, üretim başlatması kapalıdır.
