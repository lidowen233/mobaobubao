import type { Copybook, Glyph } from '@/types'

export const COPYBOOKS: Copybook[] = [
  { id: 'lantingxu', title: '兰亭序',   calligrapher: '王羲之', dynasty: '东晋', script: 'xing', source: 'system' },
  { id: 'duobao',    title: '多宝塔碑', calligrapher: '颜真卿', dynasty: '唐',   script: 'kai',  source: 'system' },
  { id: 'xuanmi',    title: '玄秘塔碑', calligrapher: '柳公权', dynasty: '唐',   script: 'kai',  source: 'system' },
  { id: 'danba',     title: '胆巴碑',   calligrapher: '赵孟頫', dynasty: '元',   script: 'kai',  source: 'system' },
]

const CHAR_VARIANTS: Record<string, string[]> = {
  '床': ['床', '牀'],
  '前': ['前'],
  '明': ['明'],
  '月': ['月'],
  '光': ['光'],
  '疑': ['疑'],
  '是': ['是'],
  '地': ['地'],
  '上': ['上'],
  '霜': ['霜'],
  '举': ['举', '舉'],
  '头': ['头', '頭'],
  '望': ['望'],
  '低': ['低'],
  '故': ['故'],
  '乡': ['乡', '鄉'],
  '静': ['静', '靜'],
  '夜': ['夜'],
  '思': ['思'],
}

const COPYBOOK_IDS = ['lantingxu', 'duobao', 'xuanmi', 'danba']

export function getGlyphsForChar(character: string): Glyph[] {
  const variants = CHAR_VARIANTS[character] ?? [character]
  return variants.map((v, i) => ({
    id: `${character}-${i}`,
    character: v,
    copybookId: COPYBOOK_IDS[i % COPYBOOK_IDS.length],
    imageUrl: '',
  }))
}

export function getCopybookById(id: string): Copybook | undefined {
  return COPYBOOKS.find((c) => c.id === id)
}
