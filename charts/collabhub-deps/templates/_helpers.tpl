{{/*
Helpers take a dict of {root, name}: every resource here belongs to one
dependency and carries that dependency's name in its labels.

Resources are named plainly — `postgres`, `redis-cache`, `dex` — rather than
prefixed with the release, so in-cluster addresses read exactly like the
Compose service names in .env.example.
*/}}

{{- define "collabhub-deps.labels" -}}
{{ include "collabhub-deps.selectorLabels" . }}
app.kubernetes.io/part-of: collabhub-deps
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end -}}

{{- define "collabhub-deps.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{/* A service's database DSN. Usage: include "collabhub-deps.dsn" (dict "root" $ "db" "auth") */}}
{{- define "collabhub-deps.dsn" -}}
{{- $pg := .root.Values.postgres -}}
{{- $password := include "collabhub-deps.credential" (dict "path" "postgres.password" "value" $pg.password) -}}
{{- printf "postgresql+asyncpg://%s:%s@postgres:5432/collabhub_%s" $pg.user $password .db -}}
{{- end -}}

{{/*
A credential that has no default. Fails the render naming the path, and how to
supply it. Usage: include "collabhub-deps.credential" (dict "path" "postgres.password" "value" .Values.postgres.password)
*/}}
{{- define "collabhub-deps.credential" -}}
{{- required (printf "%s is empty: supply it in a values file or with `scripts/deploy.sh infra -- --set-string %s=...`" .path .path) .value -}}
{{- end -}}
