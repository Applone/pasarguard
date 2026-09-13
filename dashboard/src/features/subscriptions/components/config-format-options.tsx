import { AlertCircle, Cat, CircleOff, Code, FileCode2, Globe, GlobeLock, ListTree, ShieldAlert, TriangleAlert, Unplug } from 'lucide-react'
import { type ComponentType, useMemo } from 'react'
import { WireguardIcon, XrayIcon, SingboxIcon, MihomoIcon } from '@/components/icons/format-icons'
import { useGetClientTemplatesSimple } from '@/service/api'

/**
 * Both lucide icons and the local SVG format icons accept `className`, which is all the
 * option lists render with.
 */
export type ResponseTypeIcon = ComponentType<{ className?: string }>

export const configFormatOptions = [
  { value: 'links', label: 'settings.subscriptions.configFormats.links', icon: ListTree },
  { value: 'links_base64', label: 'settings.subscriptions.configFormats.links_base64', icon: Code },
  { value: 'xray', label: 'settings.subscriptions.configFormats.xray', icon: XrayIcon },
  { value: 'wireguard', label: 'settings.subscriptions.configFormats.wireguard', icon: WireguardIcon },
  { value: 'sing_box', label: 'settings.subscriptions.configFormats.sing_box', icon: SingboxIcon },
  { value: 'clash', label: 'settings.subscriptions.configFormats.clash', icon: Cat },
  { value: 'clash_meta', label: 'settings.subscriptions.configFormats.clash_meta', icon: MihomoIcon },
  { value: 'outline', label: 'settings.subscriptions.configFormats.outline', icon: GlobeLock },
  { value: 'block', label: 'settings.subscriptions.configFormats.block', icon: CircleOff },
]

/**
 * The canonical prefix for a response type that references a Client Template. Using an
 * id keeps rules working when a template is renamed, and stops a template named e.g.
 * "CLASH" from shadowing a built-in response type.
 */
export const RESPONSE_TEMPLATE_PREFIX = 'TEMPLATE:'

/** Client template types that can render a subscription response body. */
const RESPONSE_TEMPLATE_TYPES = ['xray_subscription', 'singbox_subscription', 'clash_subscription'] as const

const TEMPLATE_TYPE_ICONS: Record<string, ResponseTypeIcon> = {
  xray_subscription: XrayIcon,
  singbox_subscription: SingboxIcon,
  clash_subscription: Cat,
}

const TEMPLATE_TYPE_LABELS: Record<string, string> = {
  xray_subscription: 'Xray',
  singbox_subscription: 'Sing-box',
  clash_subscription: 'Clash',
}

export interface ResponseTypeOption {
  value: string
  label: string
  icon: ResponseTypeIcon
  /** Present only for template-backed options. */
  templateType?: string
  missing?: boolean
}

/**
 * The built-in response types.
 *
 * These are generators and terminal behaviors, not templates — the selectable set is
 * these plus every Client Template, assembled by `useResponseTypeOptions`.
 */
export const builtinResponseTypeOptions: ResponseTypeOption[] = [
  { value: 'MIHOMO', label: 'Mihomo / Clash Meta', icon: MihomoIcon },
  { value: 'CLASH', label: 'Clash', icon: Cat },
  { value: 'STASH', label: 'Stash', icon: Cat },
  { value: 'SINGBOX', label: 'Sing-box', icon: SingboxIcon },
  { value: 'XRAY_JSON', label: 'Xray JSON', icon: XrayIcon },
  { value: 'XRAY_BASE64', label: 'Xray Base64', icon: Code },
  { value: 'LINKS', label: 'Standard Links', icon: ListTree },
  { value: 'WIREGUARD', label: 'WireGuard', icon: WireguardIcon },
  { value: 'OUTLINE', label: 'Outline / Shadowsocks', icon: GlobeLock },
  { value: 'BROWSER', label: 'Web Browser Page', icon: Globe },
  { value: 'BLOCK', label: 'Block (403 Forbidden)', icon: CircleOff },
  { value: 'STATUS_CODE_404', label: 'HTTP 404 Not Found', icon: AlertCircle },
  { value: 'STATUS_CODE_451', label: 'HTTP 451 Legal Reasons', icon: ShieldAlert },
  { value: 'SOCKET_DROP', label: 'Socket Drop (Disconnect)', icon: Unplug },
]

const BUILTIN_RESPONSE_TYPE_VALUES = new Set(builtinResponseTypeOptions.map(option => option.value))

export const isBuiltinResponseType = (value?: string | null): boolean => !!value && BUILTIN_RESPONSE_TYPE_VALUES.has(value.trim().toUpperCase())

/** The template id or name carried by a response type, or null for built-ins. */
export const responseTemplateReference = (value?: string | null): string | null => {
  const raw = (value ?? '').trim()
  if (!raw || isBuiltinResponseType(raw)) return null
  if (raw.toUpperCase().startsWith(RESPONSE_TEMPLATE_PREFIX)) {
    return raw.slice(RESPONSE_TEMPLATE_PREFIX.length).trim() || null
  }
  return raw
}

export interface UseResponseTypeOptionsResult {
  /** Built-ins followed by every selectable Client Template. */
  options: ResponseTypeOption[]
  builtins: ResponseTypeOption[]
  templates: ResponseTypeOption[]
  /** Resolve a stored value to an option, synthesizing a placeholder if it is missing. */
  resolve: (value?: string | null) => ResponseTypeOption | undefined
  isLoading: boolean
}

/**
 * Assemble the selectable response types: the built-ins plus every Client Template
 * configured in the panel. Templates are first-class response types, so adding a
 * template in Client Templates immediately makes it selectable here.
 */
export const useResponseTypeOptions = (enabled = true): UseResponseTypeOptionsResult => {
  const { data, isLoading } = useGetClientTemplatesSimple({ all: true }, { query: { enabled } })

  const templates = useMemo<ResponseTypeOption[]>(() => {
    const rows = data?.templates ?? []
    return rows
      .filter(template => RESPONSE_TEMPLATE_TYPES.includes(template.template_type as (typeof RESPONSE_TEMPLATE_TYPES)[number]))
      .map(template => ({
        value: `${RESPONSE_TEMPLATE_PREFIX}${template.id}`,
        label: template.name,
        icon: TEMPLATE_TYPE_ICONS[template.template_type] ?? FileCode2,
        templateType: template.template_type,
      }))
  }, [data?.templates])

  const options = useMemo(() => [...builtinResponseTypeOptions, ...templates], [templates])

  const resolve = useMemo(() => {
    const byValue = new Map(options.map(option => [option.value, option]))
    const byName = new Map(templates.map(option => [option.label.toLowerCase(), option]))

    return (value?: string | null): ResponseTypeOption | undefined => {
      const raw = (value ?? '').trim()
      if (!raw) return undefined

      const exact = byValue.get(raw) ?? byValue.get(raw.toUpperCase())
      if (exact) return exact

      // Accept the non-canonical spellings the API also tolerates: a bare template
      // name or id that has not been canonicalized yet.
      const reference = responseTemplateReference(raw)
      if (reference) {
        const byId = byValue.get(`${RESPONSE_TEMPLATE_PREFIX}${reference}`)
        if (byId) return byId
        const named = byName.get(reference.toLowerCase())
        if (named) return named
      }

      // The referenced template no longer exists. Surface it instead of rendering an
      // empty select, so the operator can see what broke.
      return { value: raw, label: raw, icon: TriangleAlert, missing: true }
    }
  }, [options, templates])

  return { options, builtins: builtinResponseTypeOptions, templates, resolve, isLoading }
}

export const templateTypeLabel = (templateType?: string): string | undefined => (templateType ? TEMPLATE_TYPE_LABELS[templateType] : undefined)

export const conditionOperatorOptions = [
  { value: 'EQUALS', label: 'Equals' },
  { value: 'NOT_EQUALS', label: 'Does not equal' },
  { value: 'CONTAINS', label: 'Contains' },
  { value: 'NOT_CONTAINS', label: 'Does not contain' },
  { value: 'STARTS_WITH', label: 'Starts with' },
  { value: 'NOT_STARTS_WITH', label: 'Does not start with' },
  { value: 'ENDS_WITH', label: 'Ends with' },
  { value: 'NOT_ENDS_WITH', label: 'Does not end with' },
  { value: 'REGEX', label: 'Matches Regex' },
  { value: 'NOT_REGEX', label: 'Does not match Regex' },
]

export const commonHeaderSuggestions = ['user-agent', 'accept', 'x-device-os', 'x-hwid', 'x-ver-os', 'x-device-model', 'host']
