'use client';
import Image from 'next/image';

type AvatarBot={color:string;shape:string;name:string;character?:{avatar_url:string}|null};
/** One artwork/fallback implementation for the roster, gallery and chat. */
export default function BotAvatar({bot,size='normal',working=false}:{bot:AvatarBot;size?:'small'|'normal'|'large'|'xl';working?:boolean}){
 return <span className={`avatar ${bot.color} ${bot.shape} ${size} ${working?'working':''}`} role="img" aria-label={`${bot.name}${working?' is working':''}`}>{bot.character?<Image src={bot.character.avatar_url} alt="" width={76} height={76} unoptimized/>:<span className="avatar-face"><i/><i/></span>}</span>;
}
