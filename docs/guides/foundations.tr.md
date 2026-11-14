# Kayıt, kullanım, paketler ve şartname rehberi

`gateway validate --file gateway-policy.json`, sağlayıcı protokolü/model/istek/
çıktı/byte/süre sınırlarını doğrular. `gateway self-test --image GUVENILEN_IMAJ@sha256:TAM_DIGEST --consent`,
önceden kurulu Node 20+ Linux imajında sahte anahtarla gerçek Docker sınırını dener.
Host portu açmaz, imaj indirmez, geçerli sağlayıcı isteği yapmaz; kaynaklarını kaldırır.
Worker yalnızca internal ağda kısa ömürlü erişim belirteci alır. Gerçek sağlayıcı
anahtarı gateway sürecine stdin ile verilir; dosya/ortam/argv/config/loga yazılmaz.
Süre bitince anahtarı taşıyan süreç kapanır. Bunlar protokol sınırlarıdır; kesin
dolar/fatura/abonelik kotası değildir. Native ücretli çalıştırma henüz kapalıdır.
Şema ve sınırlar [İngilizce rehberde](foundations.md#credential-gateway-checks).

İstek üst alanları ve yerel araç tanımı alanları, sağlayıcıya özgü açık izin
listeleriyle denetlenir; namespace içindeki araçlar da kapsanır. Bilinmeyen alanlar,
uzak MCP sunucusu, saklı container/bağlam, uzak araç yapılandırması ve saklı öğe
referansları transport öncesi reddedilir. Codex `client_metadata` metadata olarak
desteklenir. Bu dar metin/yerel araç sözleşmesi, tüm iç içe sağlayıcı değerlerinin
eksiksiz şema doğrulayıcısı değildir. Gerçek görev/devir kullanımı için
[kendi projede kullanım rehberine](self-use.tr.md) bakın.

`tasks sandbox GOREV --worker incelenen-worker.json --context src/app.py --consent`,
mevcut DAG'da running olan görevi, açıkça güvenilen ve digest'e sabitlenmiş yerel
imajda çevrimdışı çalıştırır. Policy şeması [İngilizce rehberdedir](foundations.md#offline-workers-and-native-checks).
İmaj indirilmez; yalnızca seçili, kapsam içi dosyaların sınırlı salt okunur snapshot'ı
verilir. Ağ/host ortamı aktarılmaz. Linux Docker daemon kısıtları başlatmadan önce
denetlenir; bellek/PID/geçici alan sınırlıdır. Zaman aşımında container zorla
kaldırılır ve yokluğu doğrulanır. Yerel dosya/görev durumu otomatik değişmez;
devir ve dosya önerilerini host inceler/test eder. Bulut Codex/Claude policy'leri,
uzak daemon ve Windows container'ları reddedilir. Docker VM değildir; host kernel
ve daemon güven sınırındadır.

`eval capabilities --provider claude --consent` yalnızca native sürüm/yardım
yeteneklerini denetler. `plugins validate --output YOL --native --consent`,
kanonik hash doğrulamasından sonra desteklenen Claude statik doğrulayıcısını
çalıştırabilir. Plugin kurulmaz/aktive edilmez, inference başlatılmaz. Ücretli
native eval ve bulut runner, kimlik bilgisi/ağ/maliyet sınırı tamamlanana kadar kapalıdır.

`eval capabilities --provider codex --image GUVENILEN_PIN --consent`, sürüm/yardım
komutlarını dış ağı kapalı container'da çalıştırır. Tam yerel `sha256:` imaj kimliği
veya repository digest'i gerekir; kısaltılmış kimlik ve değişken tag reddedilir.

`eval native-smoke --provider codex --image GUVENILEN_PIN --consent`, gerçek CLI'yi
container içindeki sabit sentetik API ile dener. Claude eşdeğeri kanonik AgentBase
plugin'ini de sağlar ve native başlangıç olayında keşfedildiğini denetler.
`--provider claude --mode eval`, native eval motorunu tek sabit prompt ve regex
grader ile çalıştırır: tek vaka/koşu/kol, eşzamanlılık 1, scaffold/yayınlama/araç/
gerçek MCP sunucusu yok. Codex eval modu reddedilir. İmajda Node 20+ ve
`/usr/local/bin/node` ile `/usr/local/bin/codex` veya `/usr/local/bin/claude`
bulunmalıdır. İmaj/binary indirilmez. Host proje/config/anahtarları verilmez;
container dış ağı kapalıdır ve yalnızca loopback sahte API kullanılır.
Rapor `origin: mock`, gerçek API çağrısı 0, gerçek model davranışı doğrulanmadı
der. Sentetik token/fiyat rakamları ve ham native izler saklanmaz. Bu test plugin
etkisi, araç yürütme veya gerçek kullanım/maliyet ölçümü değildir. Başarısız test
CLI çıkış kodu 1; girdi/kurulum/sınır/yetenek hatası 2 döndürür.
[Sınırlar ve mimari](../architecture/native-probes.md).

`explain --write` ve derin bellek eşitlemesi, dosya SHA-256'larına göre sembol,
import ve çağrı adaylarını önbelleğe alır; ham kaynak saklamaz. Değişmeyen dosyalar
yeniden ayrıştırılmaz; eklenen/silinen modüller import çözümlemesine yansır.
`explain --feature authentication`, metin eşleşmeleri ve bir adımlık import
komşularıyla hedefli harita üretir. Mermaid kanıtları dosya/satır içerir;
çalışma zamanı akışı veya anlamsal özellik keşfi doğrulanmış sayılmaz.

`local models --consent`, yapılandırılmış loopback Ollama'daki kurulu modelleri
sorgular. Öneriler öncesinde tam model adı, completion kabiliyeti, bağlam kapasitesi
ve bildirilen disk/yüklü boyut bütçeleri denetlenir. Yeni isteğe bağlı config alanları:
`context_tokens`, `max_output_tokens`, `max_model_bytes`, `max_loaded_bytes`, `structured`.
Eski config varsayılanlarla uyumludur. İstek bağlam/çıktı sınırı ve JSON şeması taşır;
yanıt rol/şema doğrulamasından geçer. `--fallback` başka sağlayıcı çağırmadan host
incelemesine yönlendirir. Öneri belleği değiştirmez. Boyut ön kontrolü OS RAM/VRAM
sınırı değildir; bağlantı zaman aşımı sunucudaki inference'ın durduğunu kanıtlamaz.
Model indirilmez, dış inference başlatılmaz.

Python 3.11+ gerekir; çalışma zamanı bağımlılığı yoktur. Komutlar hedef proje
dizininde çalışır; başka dizin için komuttan önce `--project YOL` kullanın.

## Paket seçimi

```bash
agentbase packs list
agentbase packs recommend
agentbase init --provider both --pack python --pack security --dry-run
agentbase init --provider both --pack python --pack security
agentbase packs add documentation --dry-run
agentbase packs add documentation
agentbase packs remove documentation --dry-run
agentbase doctor
```

Core otomatik seçimdir; ek paket önerileri kendiliğinden kurulmaz. Yedi paket
mevcuttur: core, web, python, ai-ml, security, devops, documentation. Paketler
mevcut kanonik rol/skill tanımlarını seçer; araç veya model indirmez, bütün
skill'leri bağlama yüklemez. Yerel değişiklik varsa işlem durur. Eski tam katalog
kurulumu korunur. `packs register --file my-pack.json --dry-run`, `packs info core`
ile aynı biçimdeki özel manifesti doğrular; ardından dry-run olmadan kaydedilebilir.
Özel paket yalnızca bilinen kanonik rol/skill'leri seçebilir; yerleşik kimlikleri
ezemez. Kaydetmek kurmaz; kimliği ayrıca `init --pack` veya `packs add` ile seçin.
`packs info` ve kurulum raporu bağımlılık varlığını kod çalıştırmadan denetler.
`tool:AD`, `python-dist:AD`, `skill:KIMLIK` bildirimleri denetlenebilir; serbest
metin bilinmiyor kalır. Varlık, kabiliyet veya sürüm uyumluluğu garantisi değildir.

## Güvenli GitHub skill kurulumu

```bash
agentbase skills
agentbase skills search verify
agentbase skills add https://github.com/owner/repository --path skills/example
# Planı, SHA'yı, lisansı, dosyaları, bağımlılıkları ve bulguları inceleyin.
agentbase skills add https://github.com/owner/repository --path skills/example --apply --plan-id INCELENEN_KIMLIK
agentbase skills info example
agentbase skills audit
agentbase skills update example
agentbase skills rollback example
agentbase skills export
agentbase skills restore skills.lock.json
agentbase skills remove example --apply
```

Varsayılan add/update/rollback/restore yalnızca plan üretir. Uygulama için tam
plan kimliği gerekir; yüksek önem dereceli her bulgu ayrıca `--acknowledge KIMLIK`
ister. Bu onay lisans hakkı sağlamaz veya kod çalıştırmaz. Değişen uzak ref yeni
inceleme gerektirir; her kurulum değişmez tam commit SHA ve dosya SHA-256'larıyla
kaydedilir. Birden çok adayda `--path` seçilir. Yerel değiştirilmiş/kayıp/eklenmiş
dosyalar güncelleme ve kaldırmayı durdurur. Son beş sürüm kaydı geri alma içindir;
snapshot'lar kaldırmadan sonra tutulur. Restore, 1..100 skill'i tek incelenen
planda toplar; tüm kaynakları yazmadan önce doğrular. Çakışma, yerel düzenleme,
eksik onay veya olağan I/O hatası kısmi kurulumu önler. İlgisiz skill'ler korunur.
96 MB hazırlama sınırı vardır. Güç/süreç kesintisi dosya sistemi transaction'ı
değildir; audit sapmayı gösterir. Arama çevrimdışı küratörlü kaynak bağlantılarını
onaylanmamış olarak listeler; bağlantılar skill güvenlik/lisans onayı değildir.
Çekirdekte `uninstall --purge` kullanmadan önce üçüncü taraf skill'leri kaldırın;
aksi halde köken kaydı kaybolmasın diye purge reddedilir.

Yalnızca herkese açık GitHub HTTPS kaynakları; yönlendirme, yol kaçışı, bağlantı,
özel dosya, çalıştırılabilir ikili ve aşırı büyük arşivler reddedilir. Betikler ve
bağımlılıklar asla otomatik çalıştırılmaz/kurulmaz. YAML desteği sınırlı güvenli
alt kümedir; desteklenmeyen yapı açık hata verir. İsteğe bağlı `agentbase-toolkit[yaml]`
ekini açıkça kurup add/update/restore için `--yaml-parser pyyaml` seçebilirsiniz.
Geniş YAML sözdiziminde de string metadata şeması korunur; alias, anchor, açık
tag, yinelenen anahtarlar ve 64 KiB üzeri frontmatter reddedilir. Eksik/çelişkili lisans çözülmemiş
kalır. Temiz tarama güvenlik garantisi değildir. [Güven modeli](../security/trust-model.md).

## İsteğe bağlı kullanım verisi

```bash
agentbase usage configure --source codex-exec-v1 --source claude-api-request-v1 --retention-days 30
agentbase usage import --file reviewed-captures.json
agentbase usage --today
agentbase usage --week --provider codex --by-agent --json --timezone UTC
agentbase usage --by-skill
agentbase usage export --format csv
agentbase usage configure
agentbase usage delete --all
```

Veri yalnızca açıkça verilen yakalama zarflarından içe alınır; otomatik sağlayıcı
bağlantısı, kimlik bilgisi okuma veya uzak analitik yoktur. Kaynaklar Codex exec,
Codex App Server, Claude OTel api_request öznitelikleri ve Claude statusline'dır.
Zarf örneği ve alanlar [İngilizce rehberde](foundations.md#usage-capture-and-privacy).
`usage capture --source claude-statusline-v1 --provider-version SURUM --project-id KIMLIK`,
stdin'den tek belgelenmiş JSON olayı alır (en fazla 1 MB). Kaynak bazında ön izin
gerekir; yalnızca izinli sayısal ölçümler/kimlikler kaydedilir. Kullanıcının kurduğu
statusline veya App Server entegrasyonu veriyi aktarır; host ayarları değiştirilmez.
Snapshot tekrarları ölçüm özetiyle ayıklanır. Artımlı exec/request olaylarında
kararlı `--session-id` ve `--event-id` gerekir; aynı sayaçlar ayrı istekler olabilir.
Gün sınırını geçen kümülatif farklar `unallocated_intervals` alanındadır; günlük
toplamlara veya başlangıcı kesen dönem toplamına kesin tüketim gibi yazılmaz.

Şartname düzenlemesinden sonra `spec reconcile KIMLIK` artımlı planı gösterir;
`--apply --plan-id INCELENEN_KIMLIK` uygular. Yalnızca bu şartnameye bağlı, henüz
başlamamış ve kanıtsız pending görevler değiştirilir/kaldırılır. Diğer görevler,
değişmemiş görev durumları ve devir kanıtları korunur. Başlamış/tamamlanmış işin
kabul ölçütünü yeniden yazmak yerine takip gereksinimi ekleyin. Yerel görev veya
üretilmiş dosya düzenlemesi işlemi durdurur. `spec evidence KIMLIK --file esleme.json`,
tam kabul metinlerini kayıtlı handoff test indeksleriyle eşler. Örnek JSON ve ayrıntılar
[İngilizce rehberdedir](foundations.md#specifications-and-evaluation). Sonuç
`reported-passed` olarak etiketlenir; AgentBase'in testi çalıştırdığı iddia edilmez.
Şartname/devir değişince eşleme eski kalır; yeniden inceleme gerekir.

Eksik sayılar null kalır; sıfır uydurulmaz. Codex kümülatif sayaçlarında ilk
ölçümün tüketim farkı bilinmez; aynı olaylar tekrar sayılmaz. Claude statusline
bağlam doluluğunu ölçer, oturum token tüketimini değil. Rol/skill atfı yalnızca
güvenilir sağlayıcı alanları veya açık AgentBase korelasyonuna dayanır. API maliyet
tahmini fatura ya da abonelik kotası değildir; kalan kota kullanılamaz gösterilir.
Codex girdi sayacı önbelleği içerir, Claude api_request girdisi içermez; ayrı
önbellek alanlarıyla birlikte yorumlayın. Gün aşan kümülatif örneklerde kesin
günlük dağılım bilinmez. [Ölçüm ayrıntıları](../architecture/usage-pipeline.md).

Depo `.agentbase/usage` altındadır. POSIX izinleri kullanıcıya özeldir; Windows
proje ACL'sini devralır. Veriyi paylaşılan dizinde tutmayın, Git'e eklemeyin.
Varsayılan saklama 30 gündür; içe alımda temizlenir, raporda süresi dolanlar
gizlenir. Kaynaksız configure içe alımı kapatır; delete veriyi siler. Ham istem,
kod, ortam değişkeni ve araç çıktısı kaydedilmez. UTC ek bağımlılık istemez;
IANA saat dilimleri sistem verisi veya isteğe bağlı tzdata gerektirir.

## Şartname, değerlendirme ve dağıtım

```bash
agentbase spec init health --title "Health API" --request "GET /health ekle" --criterion "GET /health 200 döner" --scope src
agentbase spec validate health
agentbase spec plan health --write
agentbase spec tasks health --import
agentbase eval validate
agentbase eval run
agentbase eval report
agentbase plugins build --provider claude --output packages/claude-v1
agentbase plugins validate --output packages/claude-v1
claude plugin validate packages/claude-v1
agentbase plugins build --provider codex --output packages/codex-v1
```

Markdown şartnamedeki açık gereksinimler mevcut DAG'a derlenir; yapay zekâyla
anlamsal ayrıştırma veya çelişki çözümü yapılmaz. Tamamlanma mevcut devir/kanıt
kurallarına tabidir. Mevcut görevler değiştirilmez. Değerlendirme statik yapı
kontrolü veya açıkça verilen gözlemleri puanlamadır; gerçek model aktivasyonu
iddia edilmez. Ücretli sağlayıcı değerlendirmesi başlatılmaz.

Plugin dosyaları kanonik içerikten tekrar üretilebilir; farklı mevcut dosyalar
korunur, yükseltmede yeni çıktı dizini seçilir. Python CLI ayrıca kurulmalı,
görev/bellek için projede `init --discovery plugin` yapılmalıdır; bu seçenek
plugin'in sağladığı skill ve Claude ajanlarını ayrıca üretmez. Mevcut kurulumda
önce `update --discovery plugin --dry-run`, ardından aynı komut dry-run olmadan
uygulanır; yerel düzenlemeler korunur. Codex ajanları bağımsız üretilmeye devam
eder. Yayınlama veya marketplace'e otomatik ekleme yoktur.
Gerçek sağlayıcılar arası yürütücü ve canlı ajan davranış testleri henüz yoktur.
