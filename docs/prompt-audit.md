# Rol ve skill prompt denetimi

Tarih: 2026-11-10. Kapsam: 16 rol, ortak `catalog.role_prompt`, politika ve
mevcut 7 skill. Yöntem: dosyaları okuyarak tutarlılık ve araç sözleşmesi denetimi.
Gerçek model oturumu veya prompt başarı oranı ölçümü yapılmadı.

## Bulgular ve öneriler (uygulama öncesi)

| Bulgu | Etki | Önerilen değişiklik |
|---|---|---|
| Ortak rol metninde read rolüne de tek yazıcı olarak ortak dosya yazma istisnası | Salt okuma sınırı belirsiz | Read rolü yalnızca öneri döndürsün; write rolü de ortak durum için Orchestrator'a öneri versin |
| Context Keeper belleği doğrudan güncelliyormuş gibi tanımlı | Politikanın tek yazıcı kuralıyla gerilim | İşçi çıktısı öneri, kalıcı yazım Orchestrator sorumluluğu olsun |
| QA çıktısı test değişikliği **veya** çalıştırılmış kontrol; görevin ihtiyacı belirtilmemiş | Yazılan fakat çalıştırılmayan test başarı gibi yorumlanabilir | Test değişikliği ile gözlenen koşumu ayrı raporla |
| Code Reviewer tetikleyicisi her anlamlı değişikliğe çok geniş | Gereksiz devir | Açık inceleme isteği veya bağımsız doğrulama ihtiyacı belirt |
| Plan/architecture/explain tetikleyicileri birbiriyle örtüşüyor | Küçük işte aşırı tarama | Her skill açıklamasına kullanıcı sonucu ve kapsam ayrımı ekle |
| Verify skill read rolünden de test koşumu isteyebilir | Yan etki/claim sınırı belirsiz | Read inceleyici komut önerir; yetkili yazıcı çalıştırır |
| Sync skill limitte belirsiz “remove” öneriyor | Kullanıcı notu kaybı riski | Kimlik listeleme, dry-run, gerekçe ve arşiv komutlarını kullan |
| Handoff metni `memory handoff` ile işçi devrini karıştırabilir | Kaydedilmiş kanıtın çalıştırılmış test sanılması | Oturum özeti ile görev çıktısını ayır; eksikleri açık yaz |
| Local assist çağrısında açık istek var, ama çıktı kaydetme sınırı kısa | Öneri doğrudan doğru kabul edilebilir | Kaynakla doğrulanmadan kalıcı belleğe geçirme |

Diğer roller (architect, task-planner, codebase-explorer, frontend-engineer,
backend-engineer, database-engineer, ai-ml-engineer, devops-engineer,
integration-engineer, security-reviewer, debugger, documentation-engineer,
architecture-visualizer) sorumluluk/tetikleyici/dışlama/çıktı bakımından incelendi.
Bu roller için yukarıdaki ortak metin düzeltmesi dışında somut çelişki bulunmadı.
Model ayarları ayrı #8 işinde resmî kaynaklardan kontrol edildi.

## Önerilen diff

```diff
--- catalog.role_prompt
- Do not write shared task state, contracts or memory unless explicitly assigned as the sole writer.
+ Shared task state, contracts and memory belong to the Orchestrator; return proposals.
+ Read-only roles never edit files, even when a task requests it; escalate the conflict.
--- roles.json / context-keeper
- Maintain concise evidence-backed state, decisions, open issues and session handoffs.
+ Propose concise evidence-backed state, decisions, open issues and session handoffs for the Orchestrator to record.
--- roles.json / qa-test-engineer
- Test changes or executed checks with commands, observed results and remaining gaps.
+ Scoped test changes when assigned; separately report executed commands, observed results and checks not run.
--- roles.json / code-reviewer
- A substantive change is ready for review or review is requested.
+ Review is requested, or a substantive change needs independent correctness verification.
--- skills/* / description
+ State the requested outcome and distinguish maps, explanations, task plans, checks, memory and session resume.
--- agentbase-verify-change
+ Read-only reviewers propose effectful checks; only assigned writers execute them.
--- agentbase-sync-memory
- Keep entries concise and remove superseded material thoughtfully when limits are reached.
+ Use memory list and prune/supersede --dry-run with explicit IDs and reason; preserve manual/legacy notes.
--- agentbase-session-handoff
+ This is a session resume guide; it does not complete a task or prove checks ran.
```

## Doğrulama sınırı

Öneri önce bu raporda kaydedildi. Uygulama sonrası katalog referansları ve
üretilen sağlayıcı dosyaları test edilir; gerçek ajan davranışı doğrulanmış sayılmaz.
