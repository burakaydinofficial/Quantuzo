export function parseProject(instanceId: string): string {
  const match = instanceId.match(/^(.+?__[^-]+)/);
  return match ? match[1] : instanceId;
}

export interface ProjectGroup {
  project: string;
  instanceIds: string[];
  resolved: number;
  total: number;
  rate: number;
}

export function groupByProject(
  instanceIds: string[],
  resolvedIds: Set<string>,
): ProjectGroup[] {
  const map = new Map<string, string[]>();
  for (const id of instanceIds) {
    const project = parseProject(id);
    const list = map.get(project) ?? [];
    list.push(id);
    map.set(project, list);
  }

  return Array.from(map.entries())
    .map(([project, ids]) => {
      const resolved = ids.filter((id) => resolvedIds.has(id)).length;
      return {
        project,
        instanceIds: ids,
        resolved,
        total: ids.length,
        rate: ids.length > 0 ? (resolved / ids.length) * 100 : 0,
      };
    })
    .sort((a, b) => b.total - a.total);
}
