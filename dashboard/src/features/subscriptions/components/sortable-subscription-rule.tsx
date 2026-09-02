import { responseTypeOptions } from '@/features/subscriptions/components/config-format-options'
import { SubscriptionRuleAdvancedSheet } from '@/features/subscriptions/components/subscription-rule-advanced-sheet'
import type { SubscriptionFormData } from '@/features/subscriptions/components/subscription-settings-schema'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Settings2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

export interface SortableSubscriptionRuleProps {
  index: number
  onRemove: (index: number) => void
  form: UseFormReturn<SubscriptionFormData>
  id: string
}

export function SortableSubscriptionRule({ index, onRemove, form, id }: SortableSubscriptionRuleProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false)

  const rule = form.watch(`rules.${index}`)
  const conditions = rule?.conditions || []
  const conditionCount = conditions.length
  const customTemplate = rule?.responseModifications?.subscriptionTemplate
  const headerCount = (rule?.responseModifications?.headers || []).length
  const isEnabled = rule?.enabled ?? true

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : isEnabled ? 1 : 0.6,
    direction: 'ltr' as const,
  }
  const cursor = isDragging ? 'grabbing' : 'grab'

  return (
    <>
      <div ref={setNodeRef} style={style} className="max-w-full min-w-0 cursor-default overflow-hidden" dir="ltr">
        <div className="group bg-card hover:bg-accent/20 relative flex max-w-full min-w-0 flex-col gap-2 overflow-hidden rounded-md border p-2 transition-colors sm:flex-row sm:items-center sm:gap-3 sm:p-3">
          <div className="flex min-w-0 flex-1 flex-row items-center gap-1 sm:gap-2">
            <button
              type="button"
              style={{ cursor: cursor }}
              className="active:bg-accent/40 flex min-h-[36px] min-w-[32px] shrink-0 touch-none items-center justify-center rounded-md opacity-50 transition-opacity group-hover:opacity-100 sm:min-h-0 sm:min-w-0 sm:p-0"
              {...attributes}
              {...listeners}
            >
              <GripVertical className="h-4 w-4 sm:h-5 sm:w-5" />
              <span className="sr-only">Drag to reorder</span>
            </button>

            <Switch
              checked={isEnabled}
              onCheckedChange={checked => form.setValue(`rules.${index}.enabled`, checked, { shouldDirty: true })}
              title={isEnabled ? 'Rule enabled' : 'Rule disabled'}
              className="shrink-0 scale-90"
            />

            <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5 sm:grid-cols-[minmax(0,1fr)_auto_14rem] sm:items-center sm:gap-2">
              <FormField
                control={form.control}
                name={`rules.${index}.name`}
                render={({ field }) => (
                  <FormItem className="min-w-0 space-y-0">
                    <FormLabel className="sr-only">Rule Name</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Rule name"
                        {...field}
                        className="border-muted bg-background/60 text-foreground/90 focus:bg-background h-8 w-full min-w-0 px-2.5 text-xs font-medium sm:h-8 sm:px-3"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex shrink-0 items-center gap-1.5">
                {conditionCount === 0 ? (
                  <Badge variant="outline" className="text-muted-foreground h-5 px-1.5 py-0 text-[10px]">
                    Match all
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="h-5 px-1.5 py-0 text-[10px]">
                    {conditionCount} {conditionCount === 1 ? 'condition' : 'conditions'} ({rule?.operator || 'AND'})
                  </Badge>
                )}
                {customTemplate && (
                  <Badge variant="outline" className="text-primary border-primary/30 h-5 max-w-[120px] truncate px-1.5 py-0 text-[10px]">
                    {customTemplate}
                  </Badge>
                )}
              </div>

              <div className="flex min-w-0 flex-row items-center gap-1.5 sm:contents">
                <FormField
                  control={form.control}
                  name={`rules.${index}.responseType`}
                  render={({ field }) => (
                    <FormItem className="min-w-0 flex-1 space-y-0 sm:w-[14rem] sm:shrink-0">
                      <FormLabel className="sr-only">Response Type</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value || 'XRAY_BASE64'}>
                        <FormControl>
                          <SelectTrigger dir="ltr" className="border-muted bg-background/60 focus:bg-background h-8 w-full min-w-0 px-2.5 text-[11px] sm:h-8 sm:px-3 sm:text-xs">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent dir="ltr" className="z-[50] max-h-72 scrollbar-thin">
                          {responseTypeOptions.map(option => (
                            <SelectItem key={option.value} value={option.value}>
                              <div className="flex items-center gap-1.5">
                                <option.icon className="text-muted-foreground h-3.5 w-3.5 shrink-0" />
                                <span className="text-xs">{option.label}</span>
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>
          </div>

          <div className="flex shrink-0 items-center justify-end gap-1 sm:ms-0">
            <Button type="button" variant="ghost" size="icon" className="relative h-7 w-7 sm:h-8 sm:w-8" onClick={() => setIsAdvancedOpen(true)} title="Configure Rule">
              <Settings2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              {headerCount > 0 && (
                <span
                  className="bg-primary text-primary-foreground pointer-events-none absolute -end-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full px-0.5 text-[9px] leading-none font-medium tabular-nums sm:h-4 sm:min-w-4 sm:text-[10px]"
                  aria-hidden
                >
                  {headerCount}
                </span>
              )}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={e => {
                e.preventDefault()
                e.stopPropagation()
                onRemove(index)
              }}
              className="text-destructive hover:bg-destructive/10 hover:text-destructive h-7 w-7 shrink-0 p-0 opacity-80 hover:opacity-100 sm:h-8 sm:w-8"
            >
              <Trash2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </div>

          {isDragging && <div className="border-primary/20 bg-primary/5 pointer-events-none absolute inset-0 rounded-md border" />}
        </div>
      </div>

      <SubscriptionRuleAdvancedSheet form={form} ruleIndex={index} rowId={id} open={isAdvancedOpen} onOpenChange={setIsAdvancedOpen} />
    </>
  )
}
