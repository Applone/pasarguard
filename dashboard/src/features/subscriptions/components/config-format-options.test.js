import { beforeEach, describe, expect, it, mock } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { useForm } from 'react-hook-form'

let templateResponse
let isLoading
let queryOptions
let renderedSelects = []

mock.module('@/service/api', () => ({
  useGetClientTemplatesSimple: (params, options) => {
    queryOptions = { params, options }
    return { data: templateResponse, isLoading }
  },
}))

mock.module('react-i18next', () => ({
  useTranslation: () => ({ t: (key, options) => options?.defaultValue ?? key, i18n: { dir: () => 'ltr' } }),
}))

const Container = ({ children }) => createElement('div', null, children)

mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }) => {
    renderedSelects.push({ value, onValueChange })
    return createElement('div', { 'data-select-value': value }, children)
  },
  SelectContent: Container,
  SelectGroup: Container,
  SelectLabel: ({ children }) => createElement('h3', null, children),
  SelectTrigger: Container,
  SelectValue: ({ placeholder }) => createElement('span', null, placeholder),
  SelectItem: ({ children, value, disabled }) => createElement('div', { role: 'option', 'data-value': value, 'aria-disabled': !!disabled }, children),
}))

mock.module('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }) => (open ? createElement(Container, null, children) : null),
  SheetContent: Container,
  SheetDescription: Container,
  SheetFooter: Container,
  SheetHeader: Container,
  SheetTitle: Container,
}))

mock.module('@/components/ui/tabs', () => ({
  Tabs: Container,
  TabsContent: Container,
  TabsList: Container,
  TabsTrigger: Container,
}))

mock.module('@/components/ui/variables-popover', () => ({
  CustomVariablesPopover: () => null,
  VariablesList: () => null,
}))

const { builtinResponseTypeOptions, configFormatOptions, isBuiltinResponseType, responseTemplateReference, useResponseTypeOptions } = await import('./config-format-options.tsx')
const { SortableSubscriptionRule } = await import('./sortable-subscription-rule.tsx')
const { SubscriptionRuleAdvancedSheet } = await import('./subscription-rule-advanced-sheet.tsx')
const { Form } = await import('@/components/ui/form')
const { subscriptionSchema } = await import('./subscription-settings-schema')

const builtinValues = ['BLOCK', 'STATUS_CODE_404', 'STATUS_CODE_451', 'SOCKET_DROP']
const legacyValues = ['MIHOMO', 'CLASH', 'STASH', 'SINGBOX', 'XRAY_JSON', 'XRAY_BASE64', 'LINKS', 'WIREGUARD', 'OUTLINE', 'BROWSER']

function renderOptions(enabled = true) {
  let options
  function Probe() {
    options = useResponseTypeOptions(enabled)
    return null
  }
  renderToStaticMarkup(createElement(Probe))
  return options
}

beforeEach(() => {
  templateResponse = {
    templates: [
      { id: 11, name: 'Default Clash', template_type: 'clash_subscription', is_default: true },
      { id: 12, name: 'Default Sing-box', template_type: 'singbox_subscription', is_default: true },
      { id: 13, name: 'Default Xray', template_type: 'xray_subscription', is_default: true },
      { id: 14, name: 'Custom Xray', template_type: 'xray_subscription', is_default: false },
      { id: 15, name: 'User agent', template_type: 'user_agent', is_default: true },
      { id: 16, name: 'gRPC user agent', template_type: 'grpc_user_agent', is_default: true },
    ],
    total: 6,
  }
  isLoading = false
  queryOptions = undefined
  renderedSelects = []
})

describe('subscription response options', () => {
  it('only offers HTTP errors and socket drop as built-ins', () => {
    expect(builtinResponseTypeOptions.map(option => option.value)).toEqual(builtinValues)
    expect(renderOptions().builtins.map(option => option.value)).toEqual(builtinValues)
  })

  it('lists editable subscription templates before built-ins', () => {
    const options = renderOptions()
    expect(options.templates.map(option => option.label)).toEqual(['Default Clash', 'Default Sing-box', 'Default Xray', 'Custom Xray'])
    expect(options.options.map(option => option.value)).toEqual(['TEMPLATE:11', 'TEMPLATE:12', 'TEMPLATE:13', 'TEMPLATE:14', ...builtinValues])
    expect(options.options.some(option => option.templateType === 'user_agent' || option.templateType === 'grpc_user_agent')).toBe(false)
  })

  it.each(legacyValues)('keeps saved %s responses recognizable without offering them for selection', value => {
    const options = renderOptions()
    expect(options.options.some(option => option.value === value)).toBe(false)
    expect(options.resolve(value)).toMatchObject({ value, legacy: true })
    expect(options.resolve(value).missing).toBeUndefined()
    expect(isBuiltinResponseType(value.toLowerCase())).toBe(true)
    expect(responseTemplateReference(value)).toBeNull()
  })

  it.each(builtinValues)('resolves %s without marking it as legacy or missing', value => {
    const option = renderOptions().resolve(` ${value.toLowerCase()} `)
    expect(option.value).toBe(value)
    expect(option.legacy).toBeUndefined()
    expect(option.missing).toBeUndefined()
  })

  it.each(['TEMPLATE:13', '13', 'template:13', 'Default Xray', 'template:default xray'])('resolves the template reference %s', value => {
    expect(renderOptions().resolve(value)).toMatchObject({ value: 'TEMPLATE:13', label: 'Default Xray', templateType: 'xray_subscription' })
  })

  it('keeps template names from shadowing legacy or retained built-ins', () => {
    templateResponse.templates.push({ id: 17, name: 'CLASH', template_type: 'clash_subscription', is_default: false }, { id: 18, name: 'BLOCK', template_type: 'xray_subscription', is_default: false })
    const options = renderOptions()
    expect(options.resolve('CLASH')).toMatchObject({ value: 'CLASH', legacy: true })
    expect(options.resolve('TEMPLATE:CLASH')).toMatchObject({ value: 'TEMPLATE:17' })
    expect(options.resolve('BLOCK').value).toBe('BLOCK')
    expect(options.resolve('TEMPLATE:BLOCK').value).toBe('TEMPLATE:18')
  })

  it('resolves renamed templates by their stored ID', () => {
    templateResponse.templates[2].name = 'Renamed Xray'
    expect(renderOptions().resolve('TEMPLATE:13')).toMatchObject({ value: 'TEMPLATE:13', label: 'Renamed Xray' })
  })

  it('distinguishes deleted templates from saved legacy responses', () => {
    const options = renderOptions()
    expect(options.resolve('TEMPLATE:404')).toMatchObject({ value: 'TEMPLATE:404', missing: true })
    expect(options.resolve('Deleted Template')).toMatchObject({ value: 'Deleted Template', missing: true })
    expect(options.resolve('XRAY_BASE64').missing).toBeUndefined()
    expect(options.resolve('')).toBeUndefined()
    expect(options.resolve(null)).toBeUndefined()
  })

  it('leaves the independent manual subscription formats available', () => {
    expect(configFormatOptions.map(option => option.value)).toEqual(['links', 'links_base64', 'xray', 'wireguard', 'sing_box', 'clash', 'clash_meta', 'outline', 'block'])
  })

  it('preserves loading state and query enablement', () => {
    templateResponse = undefined
    isLoading = true
    const options = renderOptions(false)
    expect(options.isLoading).toBe(true)
    expect(options.templates).toEqual([])
    expect(options.options.map(option => option.value)).toEqual(builtinValues)
    expect(options.resolve('XRAY_JSON').legacy).toBe(true)
    expect(queryOptions).toEqual({ params: { all: true }, options: { query: { enabled: false } } })
  })
})

describe('new subscription rule response', () => {
  it('prefers the default Xray client template', () => {
    expect(renderOptions().defaultResponseType).toBe('TEMPLATE:13')
  })

  it('uses another default template when Xray has no default', () => {
    templateResponse.templates[2].is_default = false
    expect(renderOptions().defaultResponseType).toBe('TEMPLATE:11')
  })

  it('uses an existing subscription template when no default is marked', () => {
    templateResponse.templates.forEach(template => {
      template.is_default = false
    })
    expect(renderOptions().defaultResponseType).toBe('TEMPLATE:11')
  })

  it('requires an explicit choice rather than defaulting to an error or removed format without templates', () => {
    templateResponse.templates = templateResponse.templates.filter(template => template.template_type === 'user_agent')
    expect(renderOptions().defaultResponseType).toBe('')
    templateResponse = undefined
    expect(renderOptions().defaultResponseType).toBe('')
  })
})

function renderSelector(component, responseType) {
  let form
  function Probe() {
    form = useForm({ defaultValues: subscriptionSchema.parse({ rules: [{ responseType }] }) })
    const props = component === SortableSubscriptionRule ? { index: 0, id: 'rule-1', onRemove: () => {} } : { ruleIndex: 0, rowId: 'rule-1', open: true, onOpenChange: () => {} }
    return createElement(Form, { ...form }, createElement(component, { ...props, form }))
  }
  const html = renderToStaticMarkup(createElement(Probe))
  form.subscribe({ formState: { values: true }, callback: () => {} })()
  return { html, form }
}

const selectableValues = html => Array.from(html.matchAll(/role="option" data-value="([^"]+)" aria-disabled="false"/g), match => match[1])

for (const [label, component] of [
  ['inline rule', SortableSubscriptionRule],
  ['advanced rule', SubscriptionRuleAdvancedSheet],
]) {
  describe(`${label} response selector`, () => {
    it('renders Client Templates before Built-in with only four built-in responses', () => {
      const { html } = renderSelector(component, 'TEMPLATE:13')
      expect(html.indexOf('Client Templates')).toBeGreaterThan(-1)
      expect(html.indexOf('Client Templates')).toBeLessThan(html.indexOf('Built-in'))
      expect(selectableValues(html).filter(value => builtinValues.includes(value))).toEqual(builtinValues)
      expect(selectableValues(html).some(value => legacyValues.includes(value))).toBe(false)
      expect(html).not.toContain('Current response (legacy)')
      expect(html).not.toContain('Missing template')
    })

    it('displays a saved legacy response without allowing it as a new selection', () => {
      const { html, form } = renderSelector(component, 'XRAY_BASE64')
      expect(html).toContain('Current response (legacy)')
      expect(html).toContain('data-value="XRAY_BASE64" aria-disabled="true"')
      expect(html).not.toContain('Missing template')
      expect(form.getValues('rules.0.responseType')).toBe('XRAY_BASE64')
    })

    it.each(['TEMPLATE:12', ...builtinValues])('persists the selectable response %s', responseType => {
      const { form } = renderSelector(component, 'XRAY_BASE64')
      const select = renderedSelects.find(select => select.value === 'XRAY_BASE64')
      expect(select).toBeDefined()
      select.onValueChange(responseType)
      expect(form.getValues('rules.0.responseType')).toBe(responseType)
    })

    it('shows missing template warnings without mislabeling them as legacy', () => {
      const { html } = renderSelector(component, 'TEMPLATE:404')
      expect(html).toContain('Missing template')
      expect(html).toContain('data-value="TEMPLATE:404"')
      expect(html).not.toContain('Current response (legacy)')
    })

    it('resolves bare template references without changing saved values on render', () => {
      const { html, form } = renderSelector(component, 'Default Xray')
      expect(html).toContain('data-select-value="TEMPLATE:13"')
      expect(html).not.toContain('Missing template')
      expect(form.getValues('rules.0.responseType')).toBe('Default Xray')
    })

    it('keeps all four terminal responses available with no client templates', () => {
      templateResponse.templates = []
      const { html } = renderSelector(component, 'BLOCK')
      expect(selectableValues(html).filter(value => builtinValues.includes(value))).toEqual(builtinValues)
      expect(html).not.toContain('>Client Templates<')
    })
  })
}
