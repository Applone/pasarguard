import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { CustomVariablesPopover, VariablesList } from '@/components/ui/variables-popover'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { useGetClientTemplatesSimple } from '@/service/api'
import { commonHeaderSuggestions, conditionOperatorOptions, responseTypeOptions } from './config-format-options'
import type { SubscriptionFormData } from './subscription-settings-schema'
import { Info, Plus, SlidersHorizontal, Trash2 } from 'lucide-react'
import { useMemo } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SubscriptionRuleAdvancedSheetProps {
  form: UseFormReturn<SubscriptionFormData>
  ruleIndex: number
  rowId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function SubscriptionRuleAdvancedSheet({ form, ruleIndex, rowId, open, onOpenChange }: SubscriptionRuleAdvancedSheetProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const infoPopoverSide = isMobile ? 'bottom' : dir === 'rtl' ? 'left' : 'right'
  const infoPopoverAlign = isMobile ? 'center' : 'start'

  const { data: templatesData } = useGetClientTemplatesSimple({ all: true }, { query: { enabled: open } })
  const templates = useMemo(() => templatesData?.templates ?? [], [templatesData?.templates])

  const rule = form.watch(`rules.${ruleIndex}`)
  const conditions = rule?.conditions || []
  const modifications = rule?.responseModifications || {
    subscriptionTemplate: null,
    headers: [],
    applyHeadersToEnd: false,
    ignoreHostXrayJsonTemplate: false,
    ignoreServeJsonAtBaseSubscription: false,
    disableHwidCheck: false,
  }
  const headers = modifications.headers || []

  const addCondition = () => {
    const nextConditions = [
      ...conditions,
      {
        headerName: 'user-agent',
        operator: 'CONTAINS' as const,
        value: '',
        caseSensitive: false,
      },
    ]
    form.setValue(`rules.${ruleIndex}.conditions`, nextConditions, { shouldDirty: true })
  }

  const updateCondition = (cIndex: number, field: string, value: any) => {
    const nextConditions = [...conditions]
    nextConditions[cIndex] = { ...nextConditions[cIndex], [field]: value }
    form.setValue(`rules.${ruleIndex}.conditions`, nextConditions, { shouldDirty: true })
  }

  const removeCondition = (cIndex: number) => {
    const nextConditions = conditions.filter((_, idx) => idx !== cIndex)
    form.setValue(`rules.${ruleIndex}.conditions`, nextConditions, { shouldDirty: true })
  }

  const addResponseHeader = () => {
    const nextHeaders = [...headers, { key: `x-header-${headers.length + 1}`, value: '' }]
    form.setValue(`rules.${ruleIndex}.responseModifications.headers`, nextHeaders, { shouldDirty: true })
  }

  const updateResponseHeader = (hIndex: number, field: 'key' | 'value', value: string) => {
    const nextHeaders = [...headers]
    nextHeaders[hIndex] = { ...nextHeaders[hIndex], [field]: value }
    form.setValue(`rules.${ruleIndex}.responseModifications.headers`, nextHeaders, { shouldDirty: true })
  }

  const removeResponseHeader = (hIndex: number) => {
    const nextHeaders = headers.filter((_, idx) => idx !== hIndex)
    form.setValue(`rules.${ruleIndex}.responseModifications.headers`, nextHeaders, { shouldDirty: true })
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={dir === 'rtl' ? 'left' : 'right'} className={cn('flex h-full max-h-screen w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-xl')} onOpenAutoFocus={e => e.preventDefault()}>
        <SheetHeader className="flex flex-shrink-0 flex-col space-y-1 border-b px-6 pe-14 pt-6 pb-4 text-start">
          <SheetTitle className="flex items-center gap-2">
            <SlidersHorizontal className="text-primary h-5 w-5" />
            {rule?.name || t('settings.subscriptions.rules.ruleSettings', { defaultValue: 'Rule Configuration' })}
          </SheetTitle>
          <SheetDescription>
            {t('settings.subscriptions.rules.ruleDescription', {
              defaultValue: 'Configure request matching conditions, response format, template overrides, and headers.',
            })}
          </SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-6 py-4">
          <Tabs defaultValue="conditions" className="flex min-h-0 flex-1 flex-col">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="conditions">
                {t('settings.subscriptions.rules.conditionsTab', { defaultValue: 'Conditions' })} ({conditions.length})
              </TabsTrigger>
              <TabsTrigger value="response">{t('settings.subscriptions.rules.responseTab', { defaultValue: 'Response' })}</TabsTrigger>
              <TabsTrigger value="headers">
                {t('settings.subscriptions.rules.headersTab', { defaultValue: 'Headers' })} ({headers.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="conditions" className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor={`rule-name-${ruleIndex}`} className="text-xs font-medium">
                    {t('settings.subscriptions.rules.name', { defaultValue: 'Rule Name' })}
                  </Label>
                  <Input
                    id={`rule-name-${ruleIndex}`}
                    value={rule?.name || ''}
                    onChange={e => form.setValue(`rules.${ruleIndex}.name`, e.target.value, { shouldDirty: true })}
                    placeholder="e.g. Happ Android / Clash Meta"
                    className="h-8 text-xs"
                  />
                </div>
                <div className="flex items-center justify-between rounded-lg border p-2">
                  <div className="space-y-0.5">
                    <Label htmlFor={`rule-enabled-${ruleIndex}`} className="text-xs font-medium">
                      {t('settings.subscriptions.rules.enabled', { defaultValue: 'Rule Enabled' })}
                    </Label>
                    <p className="text-muted-foreground text-[11px]">{t('settings.subscriptions.rules.enabledHint', { defaultValue: 'Activate or skip this rule' })}</p>
                  </div>
                  <Switch id={`rule-enabled-${ruleIndex}`} checked={rule?.enabled ?? true} onCheckedChange={checked => form.setValue(`rules.${ruleIndex}.enabled`, checked, { shouldDirty: true })} />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor={`rule-desc-${ruleIndex}`} className="text-xs font-medium">
                  {t('settings.subscriptions.rules.descriptionLabel', { defaultValue: 'Description' })}
                </Label>
                <Input
                  id={`rule-desc-${ruleIndex}`}
                  value={rule?.description || ''}
                  onChange={e => form.setValue(`rules.${ruleIndex}.description`, e.target.value, { shouldDirty: true })}
                  placeholder="Optional description"
                  className="h-8 text-xs"
                />
              </div>

              <div className="border-t pt-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Label className="text-xs font-semibold">{t('settings.subscriptions.rules.matchingLogic', { defaultValue: 'Matching Logic' })}:</Label>
                    <Select value={rule?.operator || 'AND'} onValueChange={val => form.setValue(`rules.${ruleIndex}.operator`, val as 'AND' | 'OR', { shouldDirty: true })}>
                      <SelectTrigger className="h-7 w-28 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="AND">AND (All match)</SelectItem>
                        <SelectItem value="OR">OR (Any match)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={addCondition} className="h-7 text-xs">
                    <Plus className="mr-1 h-3.5 w-3.5" />
                    {t('settings.subscriptions.rules.addCondition', { defaultValue: 'Add Condition' })}
                  </Button>
                </div>

                <div className="space-y-2.5">
                  {conditions.length === 0 ? (
                    <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-center text-xs">
                      {t('settings.subscriptions.rules.noConditionsFallback', {
                        defaultValue: 'No conditions added. This rule will match ALL clients as a fallback.',
                      })}
                    </div>
                  ) : (
                    conditions.map((cond, cIdx) => (
                      <div key={`${rowId}-cond-${cIdx}`} className="bg-card/60 space-y-2 rounded-md border p-2.5 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-muted-foreground font-semibold">#{cIdx + 1}</span>
                          <div className="flex items-center gap-2">
                            <div className="flex items-center gap-1.5">
                              <Checkbox id={`cond-cs-${ruleIndex}-${cIdx}`} checked={cond.caseSensitive ?? false} onCheckedChange={checked => updateCondition(cIdx, 'caseSensitive', !!checked)} />
                              <Label htmlFor={`cond-cs-${ruleIndex}-${cIdx}`} className="cursor-pointer text-[11px] font-normal">
                                Case sensitive
                              </Label>
                            </div>
                            <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-6 w-6" onClick={() => removeCondition(cIdx)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <div>
                            <Label className="text-muted-foreground mb-1 block text-[10px] tracking-wider uppercase">Header Name</Label>
                            <Input
                              value={cond.headerName}
                              onChange={e => updateCondition(cIdx, 'headerName', e.target.value)}
                              placeholder="e.g. user-agent, x-device-os"
                              list={`header-suggestions-${ruleIndex}`}
                              className="h-7 font-mono text-xs"
                            />
                            <datalist id={`header-suggestions-${ruleIndex}`}>
                              {commonHeaderSuggestions.map(h => (
                                <option key={h} value={h} />
                              ))}
                            </datalist>
                          </div>

                          <div>
                            <Label className="text-muted-foreground mb-1 block text-[10px] tracking-wider uppercase">Operator</Label>
                            <Select value={cond.operator} onValueChange={val => updateCondition(cIdx, 'operator', val)}>
                              <SelectTrigger className="h-7 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {conditionOperatorOptions.map(op => (
                                  <SelectItem key={op.value} value={op.value} className="text-xs">
                                    {op.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </div>

                        <div>
                          <Label className="text-muted-foreground mb-1 block text-[10px] tracking-wider uppercase">Match Value</Label>
                          <Input value={cond.value} onChange={e => updateCondition(cIdx, 'value', e.target.value)} placeholder="Value or regex pattern" className="h-7 font-mono text-xs" />
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="response" className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">{t('settings.subscriptions.rules.responseType', { defaultValue: 'Response Type' })}</Label>
                <Select value={rule?.responseType || 'XRAY_BASE64'} onValueChange={val => form.setValue(`rules.${ruleIndex}.responseType`, val as any, { shouldDirty: true })}>
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="max-h-72">
                    {responseTypeOptions.map(option => (
                      <SelectItem key={option.value} value={option.value}>
                        <div className="flex items-center gap-2">
                          <option.icon className="text-muted-foreground h-4 w-4 shrink-0" />
                          <span>{option.label}</span>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium">{t('settings.subscriptions.rules.subscriptionTemplate', { defaultValue: 'Client Template Override' })}</Label>
                <Select
                  value={modifications.subscriptionTemplate || '__DEFAULT__'}
                  onValueChange={val => form.setValue(`rules.${ruleIndex}.responseModifications.subscriptionTemplate`, val === '__DEFAULT__' ? null : val, { shouldDirty: true })}
                >
                  <SelectTrigger className="h-9 text-xs">
                    <SelectValue placeholder="Default Template" />
                  </SelectTrigger>
                  <SelectContent className="max-h-64">
                    <SelectItem value="__DEFAULT__">Default Template (from template settings)</SelectItem>
                    {templates.map(tmpl => (
                      <SelectItem key={tmpl.id} value={tmpl.name}>
                        {tmpl.name} ({tmpl.template_type})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-muted-foreground text-[11px]">
                  {t('settings.subscriptions.rules.templateHint', {
                    defaultValue: 'Specify a custom template name or ID for clients matching this rule.',
                  })}
                </p>
              </div>

              <div className="space-y-3 rounded-lg border p-3">
                <h4 className="text-foreground text-xs font-semibold">{t('settings.subscriptions.rules.advancedFlags', { defaultValue: 'Behavior Flags' })}</h4>

                <div className="flex items-center justify-between gap-2">
                  <div className="space-y-0.5">
                    <Label htmlFor={`flag-ignore-xray-${ruleIndex}`} className="text-xs font-normal">
                      Ignore Host Xray Template Override
                    </Label>
                    <p className="text-muted-foreground text-[11px]">Use the rule's template instead of host-level xray overrides</p>
                  </div>
                  <Switch
                    id={`flag-ignore-xray-${ruleIndex}`}
                    checked={modifications.ignoreHostXrayJsonTemplate ?? false}
                    onCheckedChange={checked =>
                      form.setValue(`rules.${ruleIndex}.responseModifications.ignoreHostXrayJsonTemplate`, checked, {
                        shouldDirty: true,
                      })
                    }
                  />
                </div>

                <div className="flex items-center justify-between gap-2">
                  <div className="space-y-0.5">
                    <Label htmlFor={`flag-disable-hwid-${ruleIndex}`} className="text-xs font-normal">
                      Disable HWID Check
                    </Label>
                    <p className="text-muted-foreground text-[11px]">Bypass HWID requirement and registration for this client</p>
                  </div>
                  <Switch
                    id={`flag-disable-hwid-${ruleIndex}`}
                    checked={modifications.disableHwidCheck ?? false}
                    onCheckedChange={checked =>
                      form.setValue(`rules.${ruleIndex}.responseModifications.disableHwidCheck`, checked, {
                        shouldDirty: true,
                      })
                    }
                  />
                </div>

                <div className="flex items-center justify-between gap-2">
                  <div className="space-y-0.5">
                    <Label htmlFor={`flag-apply-end-${ruleIndex}`} className="text-xs font-normal">
                      Apply Headers at End
                    </Label>
                    <p className="text-muted-foreground text-[11px]">Ensure rule headers take final precedence over subscription defaults</p>
                  </div>
                  <Switch
                    id={`flag-apply-end-${ruleIndex}`}
                    checked={modifications.applyHeadersToEnd ?? false}
                    onCheckedChange={checked =>
                      form.setValue(`rules.${ruleIndex}.responseModifications.applyHeadersToEnd`, checked, {
                        shouldDirty: true,
                      })
                    }
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="headers" className="mt-4 flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-foreground text-xs font-medium">{t('settings.subscriptions.rules.responseHeaders', { defaultValue: 'Response Headers' })}</p>
                  <p className="text-muted-foreground text-[11px]">
                    {t('settings.subscriptions.rules.responseHeadersDescription', {
                      defaultValue: 'Custom HTTP headers returned in the subscription response.',
                    })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button type="button" variant="ghost" size="icon" className="h-7 w-7">
                        <Info className="text-muted-foreground h-4 w-4" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[min(90vw,20rem)] p-3 sm:w-80" side={infoPopoverSide} align={infoPopoverAlign}>
                      <h4 className="mb-2 text-[11px] font-medium">{t('hostsDialog.variables.title')}</h4>
                      <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">
                        <VariablesList includeProfileTitle={true} includeFormat={true} />
                      </div>
                    </PopoverContent>
                  </Popover>
                  <CustomVariablesPopover customVariables={form.watch('custom_variables') || []} side={infoPopoverSide} align={infoPopoverAlign} />
                  <Button type="button" variant="outline" size="sm" onClick={addResponseHeader} className="h-7 text-xs">
                    <Plus className="mr-1 h-3.5 w-3.5" />
                    {t('settings.subscriptions.rules.addHeader', { defaultValue: 'Add Header' })}
                  </Button>
                </div>
              </div>

              <div className="space-y-2.5">
                {headers.length === 0 ? (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-xs">
                    {t('settings.subscriptions.rules.noHeaders', { defaultValue: 'No custom headers defined for this rule.' })}
                  </div>
                ) : (
                  headers.map((hdr, hIdx) => (
                    <div key={`${rowId}-hdr-${hIdx}`} className="bg-card/60 space-y-2 rounded-md border p-2.5 text-xs">
                      <div className="flex items-center gap-2">
                        <Input value={hdr.key} onChange={e => updateResponseHeader(hIdx, 'key', e.target.value)} placeholder="Header Name (e.g. x-provider-id)" className="h-7 font-mono text-xs" />
                        <Button type="button" variant="ghost" size="icon" className="text-destructive hover:bg-destructive/10 h-7 w-7 shrink-0" onClick={() => removeResponseHeader(hIdx)}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                      <Textarea
                        value={hdr.value}
                        onChange={e => updateResponseHeader(hIdx, 'value', e.target.value)}
                        placeholder="Header Value (supports {USERNAME}, {DATA_LEFT}, etc.)"
                        className="min-h-[50px] resize-none font-mono text-xs"
                        rows={2}
                      />
                    </div>
                  ))
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <SheetFooter className="flex-shrink-0 border-t px-6 py-4">
          <Button type="button" onClick={() => onOpenChange(false)}>
            {t('close', { defaultValue: 'Done' })}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
