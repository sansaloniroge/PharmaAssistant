{{- define "pharmaassistant.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "pharmaassistant.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pharmaassistant.labels" -}}
app.kubernetes.io/name: {{ include "pharmaassistant.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
