# Araçla doğrulanan görev devri

İşçi önerisini JSON olarak döndürür; Orchestrator doğrular ve görev durumuna
kaydeder. Örnek: [handoff.example.json](../examples/handoff.example.json).
Örnek `not-run` içerir; gerçek gözlemle değiştirmeden tamamlanma için kullanılamaz.

| Alan | Tür / kural |
|---|---|
| `schema_version` | Tam sayı `1` |
| `task_id` | Mevcut hedef görevin kimliği |
| `result` | Boş olmayan sonuç açıklaması |
| `changed_files` | POSIX göreli dosya yolları; yalnızca görevin yazma kapsamı, tekrar yok |
| `decisions` | Metin listesi; karar yoksa `[]` |
| `tests` | En az bir `{command, status, outcome}` nesnesi |
| `failures` | Çözülmemiş hatalar; yoksa `[]` |
| `risks` | Kalan riskler; yoksa `[]` |
| `artifacts` | Bağımlıların ihtiyaç duyduğu çıktı referansları; yoksa `[]` |

Test `status`: `passed`, `failed`, `not-run`. `command` ve `outcome` boş olamaz;
çalıştırılmadıysa outcome gerekçeyi belirtir. Statik inceleme de gözlemini açıkça
anlatarak kaydedilebilir. Salt okuma rolünün changed_files alanı boş kalır.
Sınır: yapı, kimlik, kapsam ve karakter bütçesi kontrol edilir; araç komutları
çalıştırmaz, metnin doğruluğunu veya artifact'in varlığını kanıtlamaz.

```bash
agentbase tasks validate-handoff --file handoff.json
agentbase tasks transition TASK_ID review --handoff-file handoff.json
agentbase tasks transition TASK_ID completed --evidence "gözlenen kontrol ve sonuç"
```

`review` için geçerli devir gerekir. `completed`, kaydedilmiş devri kullanır;
yenisini `--handoff-file` ile vermek de mümkündür. Tamamlanmada en az bir passed
gözlemi, hiç failed kontrol/çözülmemiş failure olmaması ve ayrıca verification
kanıtı gerekir. Kabul kriterlerini değerlendirmek hâlâ Orchestrator'ın işidir;
not-run olarak kalan kontroller otomatik başarılı sayılmaz.

Devir `tasks.json` içindeki ilgili görevin isteğe bağlı `handoff` alanında,
durumla aynı atomik yazımda saklanır. Hatalı devirde durum/claim değişmez.
`review -> running` eski devir ve verification kanıtını temizler; yeniden
review için yeni devir gerekir. Blocked/failed/pending geçişleri de devri kaldırır.

Şema-v1 eski planlar okunabilir kalır. Devirsiz tarihî completed görevler,
`tasks validate` çıktısında `legacy_completed_without_handoff` ve `doctor`
uyarısında gösterilir; bunlar sonradan doğrulanmış sayılmaz. Yeni CLI review ve
tamamlanma geçişleri zorunlu kontrolü uygular. Plan dosyasını elle değiştirmek,
diğer AgentBase claim'lerinde olduğu gibi çalışma zamanı korumasıyla engellenmez.
