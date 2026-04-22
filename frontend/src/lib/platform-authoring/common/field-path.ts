export type FieldPath = string;

export function joinFieldPath(path: FieldPath, segment: string): FieldPath {
  if (!path) {
    return segment;
  }

  return segment.startsWith("[") ? `${path}${segment}` : `${path}.${segment}`;
}
