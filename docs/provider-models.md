# Rol başına model ve efor

Resmî belge kontrolü: 2026-11-10. Bunlar başlangıç önerileridir; kalite ve
maliyet ölçümü yapılmadı. Model erişimi hesaba, sağlayıcıya ve istemciye bağlıdır.

| İş | Codex | Claude Code |
|---|---|---|
| Basit okuyucu | `gpt-6-luna`, `low` | `haiku`, `low` |
| Mimar / güvenlik | `gpt-6.1-sol`, `high` | `opus`, `high` |
| Uygulama / bilgi bakımı | `gpt-6.1-sol`, `medium` | `sonnet`, `medium` |

Kaynak tek yerdedir: `assets/roles.json` içindeki `model_recommendations`.
`agentbase update --dry-run` mevcut projeye uygulanacak değişiklikleri gösterir.
Yerel değiştirilmiş yönetilen dosyalar korunur; otomatik model çağrısı yapılmaz.

- [Codex özel ajan şeması](https://learn.chatgpt.com/docs/agent-configuration/subagents):
  TOML içinde `model` ve `model_reasoning_effort` desteklenir; `low`, `medium`,
  `high` belgelenmiştir. Basit okuyucu için düşük efor seçimi AgentBase önerisidir.
- [Codex modelleri](https://learn.chatgpt.com/docs/models): Luna daha hafif işler,
  Sol daha karmaşık işler içindir; model kimlikleri burada doğrulandı.
- [Claude Code alt ajan şeması](https://code.claude.com/docs/en/sub-agents):
  frontmatter içinde `model` ve `effort` desteklenir.
- [Claude Code model ayarları](https://code.claude.com/docs/en/model-config):
  `haiku`, `sonnet`, `opus` geçerli takma adlardır; güncel Anthropic API
  eşlemesi 5.5 ailesidir. Takma adlar sürüm ve sağlayıcıya göre değişebilir.

Doğrulanmadı: bu dosyaların gerçek Codex/Claude Code oturumunda yüklenmesi,
hesabın model erişimi ve eski istemcilerde davranış. Belgede bulunmayan alan eklenmedi.
