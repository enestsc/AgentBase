# Third-party notices

No third-party skill or reference-project code is bundled by this change.
AgentBase's runtime remains Python standard library only. Reference links do
not grant rights to linked content; see the [reference/license audit](docs/decisions/reference-audit.md).

Skills installed separately by users retain their own licenses. The installer
preserves available repository/ancestor and skill-level license and attribution
files under each skill's `source-notices/` directory and records the inventory
and source commit in `.agentbase/skills.lock.json`. Unrecognized, conflicting or
restricted licenses remain unresolved. Per-dependency licenses require their own
review; AgentBase never installs the declared dependencies automatically.

The opt-in live installer smoke tests a pinned MIT-identified skill from
obra/superpowers in a disposable temporary directory; none of that skill's
content is redistributed in AgentBase.

Local native CLI smoke preparation used official Codex/Claude binary archives
only as ignored developer artifacts; no native binary/archive is included in the
AgentBase wheel or source distribution. Their own notices and provenance remain
with the local image inputs. Codex's package metadata declares Apache-2.0;
Claude's binary carries Anthropic proprietary terms. AgentBase's MIT license
does not apply to those separately acquired binaries. See the dated
[local verification record](docs/development/STATUS.md).
