// API paths verified against app/routes. Public captive routes are intentionally separate from staff routes.
export const API={
  baseUrl:()=>{const saved=localStorage.getItem('dz_api_base')||localStorage.getItem('hotspot_api_base');if(saved)return saved.replace(/\/$/,'');if(location.protocol==='file:')return'http://localhost:8000';if(['5500','5501','5502','3000','4173','5173'].includes(location.port))return`${location.protocol}//${location.hostname}:8000`;return location.origin},
  auth:{login:'/api/v1/auth/login',refresh:'/api/v1/auth/refresh',me:'/api/v1/auth/me',logout:'/api/v1/auth/logout'},
  portal:{plans:'/api/v1/hotspot/plans/public',purchase:'/api/v1/hotspot/purchase',status:'/api/v1/hotspot/purchase/status',deviceLookup:'/api/v1/hotspot/devices/lookup',deviceAttest:'/api/v1/hotspot/devices/attest',voucherCheck:'/api/v1/vouchers/public/check',trial:'/api/v1/hotspot/free-trial'},
  dashboard:'/api/v1/dashboard/summary',customers:'/api/v1/customers',servicePlans:'/api/v1/services',catalogPackages:'/api/v1/packages',invoices:'/api/v1/invoices',payments:'/api/v1/payments',mpesa:'/api/v1/mpesa',vouchers:'/api/v1/vouchers',devices:'/api/v1/routers',tickets:'/api/v1/support/tickets'
};
