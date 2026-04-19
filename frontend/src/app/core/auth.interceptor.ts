import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthApi } from './auth-api';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthApi);
  const router = inject(Router);

  const token = auth.token();
  const authed = token && req.url.startsWith('http://localhost:8080')
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authed).pipe(
    catchError(err => {
      if (err?.status === 401 && auth.isAuthenticated()) {
        auth.logout();
        router.navigate(['/login']);
      }
      return throwError(() => err);
    })
  );
};
