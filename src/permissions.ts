import type {User} from './types';

const publicPermissions = new Set(['traffic.view','forecast.view','routes.search','warnings.view']);

export function can(user:User|null, permission:string) {
  return user ? user.permissions?.includes(permission) ?? false : publicPermissions.has(permission);
}

export const managementSections = ['monitor.view','incidents.view','publication.view','rules.view'];
