# Security Policy

## Bildirim

Güvenlik açığı bulduysanız herkese açık issue açmayın. GitHub'da bu depo için
[Private vulnerability reporting](https://github.com/enestsc/AgentBase/security/advisories/new)
üzerinden bildirin.

## Kapsam

AgentBase yerel bir koordinasyon aracıdır; sandbox veya izin sistemi değildir.
Kapsamdaki konular: proje kökü dışına yazma (path confinement), symlink kaçışı,
yönetilen dosyaların kullanıcı içeriğini ezmesi, gizli dosyaların bağlama sızması
ve yerel model çağrılarının loopback dışına gitmesi.
Sağlayıcı çalışma zamanı (Codex / Claude Code) davranışı kapsam dışıdır.
