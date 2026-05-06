export class Scheduler {
  async parallel<T extends readonly unknown[]>(tasks: { [K in keyof T]: () => Promise<T[K]> }): Promise<T> {
    return Promise.all(tasks.map(task => task())) as unknown as Promise<T>;
  }

  async sequential<T>(tasks: Array<() => Promise<T>>): Promise<T[]> {
    const results: T[] = [];
    for (const task of tasks) {
      results.push(await task());
    }
    return results;
  }
}
