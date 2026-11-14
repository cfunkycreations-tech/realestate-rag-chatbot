/** Names and jobs are distinct; archetypes are never substituted for jobs. */
export type Identity = {name:string;title:string};
export function jobTitle(bot:Identity):string{return bot.title.trim() || 'No job title'}
export function identityLabel(bot:Identity):string{return `${bot.name} — ${jobTitle(bot)}`}
