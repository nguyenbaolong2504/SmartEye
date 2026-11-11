import type {User} from './types';

const publicPermissions = new Set(['traffic.view','forecast.view','routes.search','warnings.view','cameras.view']);

export function can(user:User|null, permission:string) {
  return user ? user.permissions?.includes(permission) ?? false : publicPermissions.has(permission);
}

export function hasTrafficConfiguration(user:User|null) {
  return Boolean(user && (['sources.manage','network.manage','models.manage'].some(permission=>can(user,permission)) ||
    (user.managed_segment_ids==null && can(user,'diagnostics.view'))));
}

export function hasManagement(user:User|null) {
  return ['monitor.view','incidents.view','publication.view','rules.view','analytics.view'].some(permission=>can(user,permission)) ||
    hasTrafficConfiguration(user);
}
