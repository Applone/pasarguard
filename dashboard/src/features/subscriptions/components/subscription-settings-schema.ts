import { z } from 'zod'

export const builtInVariableKeys = [
  'SERVER_IP',
  'SERVER_IPV6',
  'USERNAME',
  'DATA_USAGE',
  'DATA_LIMIT',
  'DATA_LEFT',
  'DAYS_LEFT',
  'EXPIRE_DATE',
  'JALALI_EXPIRE_DATE',
  'TIME_LEFT',
  'STATUS_EMOJI',
  'USAGE_PERCENTAGE',
  'ADMIN_USERNAME',
  'PROFILE_TITLE',
  'PROTOCOL',
  'TRANSPORT',
  'URL',
  'FORMAT',
] as const

export const customVariableSchema = z.object({
  key: z
    .string()
    .max(64, 'Variable key must be 64 characters or less')
    .regex(/^$|^[A-Z][A-Z0-9_]*$/, 'Use uppercase letters, numbers, and underscores')
    .default(''),
  value: z.string().max(512, 'Variable value must be 512 characters or less').default(''),
})

export const customVariablesSchema = z
  .array(customVariableSchema)
  .default([])
  .superRefine((variables, ctx) => {
    const seen = new Set<string>()
    for (const [index, variable] of variables.entries()) {
      if (!variable.key) continue
      if ((builtInVariableKeys as readonly string[]).includes(variable.key)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Custom variable conflicts with a built-in variable',
          path: [index, 'key'],
        })
      }
      if (seen.has(variable.key)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Duplicate custom variable',
          path: [index, 'key'],
        })
      }
      seen.add(variable.key)
    }
  })

export const normalizeCustomVariablesForPayload = (variables?: { key?: string; value?: string }[] | null) =>
  (variables || [])
    .map(variable => ({
      key: variable.key?.trim() || '',
      value: variable.value?.trim() || '',
    }))
    .filter(variable => variable.key)

export const subscriptionApplicationSchema = z.object({
  name: z.string().min(1, 'Application name is required').max(32, 'Application name must be 32 characters or less'),
  icon_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  import_url: z
    .string()
    .refine(
      url => {
        if (!url || url === '') return true
        return url.includes('{url}')
      },
      {
        message: 'Import URL must contain {url} placeholder for URL replacement',
      },
    )
    .optional()
    .or(z.literal('')),
  description: z.record(z.string()).optional(),
  recommended: z.boolean().optional(),
  show_when_hwid_enabled: z.boolean().optional(),
  platform: z.enum(['android', 'ios', 'windows', 'macos', 'linux', 'appletv', 'androidtv']),
  download_links: z
    .array(
      z.object({
        name: z.string().min(1, 'Download link name is required').max(64, 'Download link name must be 64 characters or less'),
        url: z.string().url('Please enter a valid URL'),
        language: z.enum(['fa', 'en', 'ru', 'zh']),
      }),
    )
    .min(1, 'At least one download link is required'),
})

export type SubscriptionApplicationFormData = z.infer<typeof subscriptionApplicationSchema>

export const subscriptionSchema = z.object({
  url_prefix: z.string().optional(),
  update_interval: z.number().min(1, 'Update interval must be at least 1 hour').max(168, 'Update interval cannot exceed 168 hours (1 week)').optional(),
  support_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  profile_title: z.string().optional(),
  announce: z.string().max(128, 'Announcement must be 128 characters or less').optional(),
  announce_url: z.string().optional().or(z.literal('')),
  allow_browser_config: z.boolean().optional(),
  disable_sub_template: z.boolean().optional(),
  randomize_order: z.boolean().optional(),
  custom_variables: customVariablesSchema,
  response_headers: z.record(z.string()).optional(),
  rules: z.array(
    z.object({
      name: z.string().max(50).default(''),
      description: z.string().max(250).default(''),
      enabled: z.boolean().default(true),
      operator: z.enum(['AND', 'OR']).default('AND'),
      conditions: z
        .array(
          z.object({
            headerName: z.string().min(1, 'Header name is required'),
            operator: z.enum(['EQUALS', 'NOT_EQUALS', 'CONTAINS', 'NOT_CONTAINS', 'STARTS_WITH', 'NOT_STARTS_WITH', 'ENDS_WITH', 'NOT_ENDS_WITH', 'REGEX', 'NOT_REGEX']).default('CONTAINS'),
            value: z.string().default(''),
            caseSensitive: z.boolean().default(false),
          }),
        )
        .default([]),
      responseType: z
        .enum(['MIHOMO', 'CLASH', 'STASH', 'SINGBOX', 'XRAY_JSON', 'XRAY_BASE64', 'LINKS', 'WIREGUARD', 'OUTLINE', 'BROWSER', 'BLOCK', 'STATUS_CODE_404', 'STATUS_CODE_451', 'SOCKET_DROP'])
        .default('XRAY_BASE64'),
      responseModifications: z
        .object({
          subscriptionTemplate: z.string().nullable().optional(),
          headers: z
            .array(
              z.object({
                key: z.string().min(1, 'Header key is required'),
                value: z.string().default(''),
              }),
            )
            .default([]),
          applyHeadersToEnd: z.boolean().default(false),
          ignoreHostXrayJsonTemplate: z.boolean().default(false),
          ignoreServeJsonAtBaseSubscription: z.boolean().default(false),
          disableHwidCheck: z.boolean().default(false),
        })
        .default({
          subscriptionTemplate: null,
          headers: [],
          applyHeadersToEnd: false,
          ignoreHostXrayJsonTemplate: false,
          ignoreServeJsonAtBaseSubscription: false,
          disableHwidCheck: false,
        }),
    }),
  ),
  applications: z.array(subscriptionApplicationSchema).optional(),
  manual_sub_request: z
    .object({
      links: z.boolean().optional(),
      links_base64: z.boolean().optional(),
      xray: z.boolean().optional(),
      wireguard: z.boolean().optional(),
      sing_box: z.boolean().optional(),
      clash: z.boolean().optional(),
      clash_meta: z.boolean().optional(),
      outline: z.boolean().optional(),
    })
    .optional(),
})

export type SubscriptionFormData = z.infer<typeof subscriptionSchema>
export type SubscriptionRuleFormData = SubscriptionFormData['rules'][number]
export type SubscriptionPlatform = SubscriptionApplicationFormData['platform']
export type SubscriptionLanguage = NonNullable<SubscriptionApplicationFormData['download_links']>[number]['language']

export const defaultSubscriptionRules: SubscriptionRuleFormData[] = [
  {
    name: 'Clash Meta / Mihomo',
    description: 'Serve Mihomo YAML configuration',
    enabled: true,
    operator: 'AND',
    conditions: [
      {
        headerName: 'user-agent',
        operator: 'REGEX',
        value: '^(?:FlClashX?|Flowvy|[Cc]lash(?:-(?:[Vv]erge|nyanpasu)|X [Mm]eta|-?[Mm]eta)|[Kk]oala-[Cc]lash|[Mm](?:urge|ihomo)|prizrak-box|clash\\.meta)',
        caseSensitive: true,
      },
    ],
    responseType: 'MIHOMO',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
  {
    name: 'Clash / Stash',
    description: 'Serve Clash YAML configuration',
    enabled: true,
    operator: 'AND',
    conditions: [
      {
        headerName: 'user-agent',
        operator: 'REGEX',
        value: '^([Cc]lash|[Ss]tash)',
        caseSensitive: true,
      },
    ],
    responseType: 'CLASH',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
  {
    name: 'Sing-box',
    description: 'Serve Sing-box JSON configuration',
    enabled: true,
    operator: 'AND',
    conditions: [
      {
        headerName: 'user-agent',
        operator: 'REGEX',
        value: '^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\\-b]?ox.*',
        caseSensitive: true,
      },
    ],
    responseType: 'SINGBOX',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
  {
    name: 'Outline / Shadowsocks',
    description: 'Serve Outline / Shadowsocks configuration',
    enabled: true,
    operator: 'AND',
    conditions: [
      {
        headerName: 'user-agent',
        operator: 'REGEX',
        value: '^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)',
        caseSensitive: true,
      },
    ],
    responseType: 'OUTLINE',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
  {
    name: 'Xray / InHive / V2Ray',
    description: 'Serve Xray JSON configuration',
    enabled: true,
    operator: 'AND',
    conditions: [
      {
        headerName: 'user-agent',
        operator: 'REGEX',
        value: '^[Ii]n[Hh]ive|^([Vv]2rayNG|[Vv]2rayN|[Ss]treisand|[Hh]app|[Kk]tor\\-client)',
        caseSensitive: true,
      },
    ],
    responseType: 'XRAY_JSON',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
  {
    name: 'Web Browser',
    description: 'Serve HTML subscription page for browsers',
    enabled: true,
    operator: 'AND',
    conditions: [
      {
        headerName: 'accept',
        operator: 'CONTAINS',
        value: 'text/html',
        caseSensitive: false,
      },
    ],
    responseType: 'BROWSER',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
  {
    name: 'Default Fallback',
    description: 'Fallback rule for all other clients',
    enabled: true,
    operator: 'AND',
    conditions: [],
    responseType: 'XRAY_BASE64',
    responseModifications: {
      subscriptionTemplate: null,
      headers: [],
      applyHeadersToEnd: false,
      ignoreHostXrayJsonTemplate: false,
      ignoreServeJsonAtBaseSubscription: false,
      disableHwidCheck: false,
    },
  },
]
