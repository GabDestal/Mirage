// The one import site for agent avatars. Swap the path to '@/agents/avatars' once it lands.
export { AgentAvatar } from '@/agents/avatars.stub'

export type AvatarState = 'working' | 'idle' | 'waiting' | 'frozen' | 'killed' | 'mirage'
