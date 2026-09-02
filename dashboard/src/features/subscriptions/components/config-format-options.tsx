import { AlertCircle, Cat, CircleOff, Code, Globe, GlobeLock, ListTree, ShieldAlert, Unplug } from 'lucide-react'
import { WireguardIcon, XrayIcon, SingboxIcon, MihomoIcon } from '@/components/icons/format-icons'

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

export const responseTypeOptions = [
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
