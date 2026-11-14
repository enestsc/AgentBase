# Yerel host test makbuzları

`tasks test` yalnız operatörün açıkça verdiği argv listesini çalıştırır. Güvenilen
yürütülebilir dosya ve argümanları inceleyin, mevcut DAG'da **running durumunda
yazma claim'i olan** bir görev seçin ve `--consent` verin. Görev/spec/devir
metinlerindeki komutlar yürütülmez. Komut host kullanıcısının dosya ve ağ haklarıyla
çalışır; kapsam ve sınırlı ortam **sandbox değildir**. Zorlanan çevrimdışı sınır
gerekiyorsa ayrı Docker worker kullanılmalıdır.

Görev kapsamını hazırladıktan sonra PowerShell örneği:

```powershell
$python = (Get-Command python).Source
agentbase tasks test TASK_ID --source src --source tests --source pyproject.toml --pythonpath src --timeout 120 --consent --argv $python -m unittest discover -s tests
agentbase tasks receipt RECEIPT_ID
```

`--argv` son seçenektir; sonrası literal argümandır. Mutlak yürütülebilir yol
gerekir; Windows'ta yol çözülmeden önce ve sonra yalnız native `.exe` kabul edilir;
batch/script hedefleri reddedilir. Kanonik DAG yazıcıları
sıraya alır; proje kilidi yürütme ve kayıt boyunca tutulur. Argümanlara sır
koymayın: makbuz yalnız argv hash'ini saklasa bile süreç/işletim sistemi bunları görür.

`.agentbase/receipts/` altındaki yönetilen makbuz; görev kimliği ve statik tanım
hash'ini (kabul, kapsam, bağımlılıklar, kaynak claim'leri), seçilen dosya envanterini,
yürütülebilir yol/hash'ini, argv hash'ini, açık Python import yollarını, zaman
sınırını, UTC başlangıcı, süreyi, çıkış kodunu ve çıktı toplama durumunu saklar.
Görev durumu/devir gibi çalışma zamanı alanları hash dışında kalır. stdout/stderr
için akış başına en fazla 1 MB'ın byte sayısı ve SHA-256'sı tutulur; ham çıktı,
literal argv ve ortam değerleri saklanmaz.

Kaynaklar, görev tanımı ve yürütülebilir dosya öncesi/sonrası kontrol edilir.
`tasks receipt` aynı kökleri yeniden tarar; değişen, eklenen, silinen, okunamayan
veya link olan dosya kaydı stale yapar. Çalışma sonrası okunamayan bağlar,
başarısız çıkış, zaman aşımı, çıktı taşması veya eksik pipe toplama başarı sayılmaz.
Başarı 0, başarısız/stale rapor 1, reddedilen giriş/izin veya başlatma hatası 2
döndürür; başlatma hatasında yürütme makbuzu oluşmaz. Eski kayıtlar korunur.

Görev kapsamında 1..50 örtüşmeyen proje-göreli dosya/dizin seçilebilir. Sınırlar:
2.000 dosya, 5.000 ziyaret edilen girdi, derinlik 50, dosya başına 1 MB ve toplam
16 MB. Link/junction, özel dosya, büyük/küçük harf çakışması ve yaygın sır yolları
reddedilir. Dizin altında `.git`, `.agentbase`, `node_modules`, build ve
`__pycache__` gibi standart context istisnaları atlanır; açıkça seçilmeleri
reddedilir. Boş envanter başarısızdır. Yalnız seçilen byte'lar bağlanır; ilgili
config, fixture ve lock dosyalarını açıkça ekleyin. Harici kütüphane/araçlar,
interpreter modülleri ve dış kaynakların **içeriği** hash'lenmez; resource yalnız
claim tanımını bağlar.

Alt süreç sistem/temp değerleri, dar executable/system PATH, kapalı user-site ve
bytecode ile seçilen kaynak altındaki açık `--pythonpath` dizinlerini alır.
Host credential'ları ve operatör PYTHONPATH'i aktarılmaz. PATH dışındaki araçlar
bulunmayabilir, testler isteğe bağlı kontrolleri atlayabilir; gerçek test sayısı ve
sonuçlarını ayrıca inceleyin. Çıkış 0 kabul kapsamını kanıtlamaz.

Zaman/çıktı sınırında yalnız doğrudan alt süreç sonlandırılır; pipe beklemeleri
sınırlıdır. Torun süreç temizliği **doğrulanmaz**; torunlar host haklarıyla kalabilir.
Kilit işbirlikçidir; geçici değişip geri alınan dosyalar tespit edilemez. Makbuz ve
manifest'i birlikte değiştirebilen yerel kişi kayıt uydurabilir: hash'ler olağan
drift'i saptar, bağımsız veya kriptografik kimliği doğrulanmış kanıt sağlamaz.
Proje ACL'lerini koruyun. Değişmiş/kayıp yönetilen makbuzlar yeni okuma/çalışmayı
durdurur; izlenmeyen yollar korunur. Depo üst sınırı 1.000 makbuzdur.

Makbuz görev durumunu veya `spec evidence`/devir gözlemlerini otomatik yükseltmez.
Kabul eşlemesi ve doğrulanmış devir hâlâ koordinatörün açık işidir.
