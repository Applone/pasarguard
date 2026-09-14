import { describe, expect, it } from 'bun:test'

import { defaultSubscriptionRules } from './subscription-settings-schema'

const matchDefaultRule = (userAgent: string) => {
  const matched = defaultSubscriptionRules.find(rule =>
    rule.enabled &&
    rule.conditions?.some(c =>
      c.headerName.toLowerCase() === 'user-agent' &&
      c.operator === 'REGEX' &&
      new RegExp(c.value, c.caseSensitive ? undefined : 'i').test(userAgent)
    )
  )
  return matched?.responseType ?? 'XRAY_BASE64'
}

describe('default subscription rules', () => {
  it('uses the first matching rule for built-in clients', () => {
    expect(matchDefaultRule('v2rayN/7.15')).toBe('LINKS')
    expect(matchDefaultRule('v2rayNG/1.10')).toBe('LINKS')
    expect(matchDefaultRule('Happ/2.0')).toBe('XRAY_JSON')
    expect(matchDefaultRule('Streisand/1.0')).toBe('XRAY_JSON')
    expect(matchDefaultRule('ktor-client/2.3')).toBe('XRAY_JSON')
  })

  it('keeps other clients on the catch-all and has no InHive rule', () => {
    expect(matchDefaultRule('InHive/1.0')).toBe('XRAY_BASE64')
    expect(matchDefaultRule('unknown-client/1.0')).toBe('XRAY_BASE64')
    expect(defaultSubscriptionRules.some(rule => rule.conditions?.some(c => /inhive/i.test(c.value)))).toBe(false)
  })
})
