/** Reading Dungeon's City JSON schema (from pydantic) to build forms: field kinds, enums and references. */
export interface JsonSchema {
  type?: string | string[]
  enum?: string[]
  items?: JsonSchema
  properties?: Record<string, JsonSchema>
  required?: string[]
  $ref?: string
  anyOf?: JsonSchema[]
  maxLength?: number
  default?: unknown
  title?: string
  $defs?: Record<string, JsonSchema>
  additionalProperties?: boolean | JsonSchema
}

export type FieldKind = 'text' | 'long' | 'number' | 'boolean' | 'choice' | 'choices' | 'list' | 'json'

/** A schema with its $ref and nullable anyOf unwrapped. */
export function resolve(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (schema.$ref) return resolve(root.$defs?.[schema.$ref.split('/').pop() ?? ''] ?? {}, root)
  if (schema.anyOf) {
    const real = schema.anyOf.filter((option) => option.type !== 'null')
    if (real.length === 1) return resolve(real[0], root)
  }
  return schema
}

export function fieldKind(raw: JsonSchema, root: JsonSchema): FieldKind {
  const schema = resolve(raw, root)
  if (schema.enum) return 'choice'
  if (schema.type === 'string') return (schema.maxLength ?? 0) > 120 || !schema.maxLength ? 'long' : 'text'
  if (schema.type === 'number' || schema.type === 'integer') return 'number'
  if (schema.type === 'boolean') return 'boolean'
  if (schema.type === 'array') {
    const item = resolve(schema.items ?? {}, root)
    if (item.enum) return 'choices'
    if (item.type === 'string') return 'list'
  }
  return 'json'
}

/** City list sections worth a tab, in the order an author fills a town in, with what each holds. */
export const CITY_SECTIONS: { key: string; name: string; label: string }[] = [
  { key: 'neighborhoods', name: 'Neighborhoods', label: 'Districts of the town' },
  { key: 'places', name: 'Places', label: 'Where scenes happen: taverns, shrines, shops, squares' },
  { key: 'notables', name: 'Notables', label: 'Named people placed in town' },
  { key: 'employers', name: 'Employers', label: 'Who hires' },
  { key: 'careers', name: 'Careers', label: "Jobs particular to this town" },
  { key: 'prices', name: 'Prices', label: 'What things cost here' },
  { key: 'local_color', name: 'Local color', label: 'Customs, sayings, rumours' },
  { key: 'annual_events', name: 'Events', label: 'Yearly festivals and days' },
  { key: 'transit', name: 'Transit', label: 'How people get around' },
  { key: 'career_hubs', name: 'Career hubs', label: 'Where the work clusters' },
]

/** Fields that name another record, so the form offers a pick list: field -> where its choices come from. */
export const REFERENCES: Record<string, 'neighborhoods' | 'places' | 'sources' | 'transit' | 'careers'> = {
  neighborhood: 'neighborhoods', neighborhoods: 'neighborhoods', place: 'places', places: 'places',
  source: 'sources', transit: 'transit',
}

export const blankFor = (item: JsonSchema, root: JsonSchema, defaults: Record<string, unknown>): Record<string, unknown> => {
  const schema = resolve(item, root)
  const blank: Record<string, unknown> = {}
  for (const name of schema.required ?? []) {
    const kind = fieldKind(schema.properties?.[name] ?? {}, root)
    const field = resolve(schema.properties?.[name] ?? {}, root)
    if (name in defaults) blank[name] = defaults[name]
    else if (kind === 'choice') blank[name] = field.enum?.[0]
    else if (kind === 'choices') blank[name] = field.enum?.slice(0, 1)
    else if (kind === 'list') blank[name] = []
    else if (kind === 'number') blank[name] = 0
    else if (kind === 'boolean') blank[name] = false
    else if (kind === 'json') blank[name] = field.type === 'array' ? [] : {}
    else blank[name] = ''
  }
  return blank
}
