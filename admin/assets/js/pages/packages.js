Pages.packages = makeSimpleCrudPage({
  title: 'Package',
  endpoint: '/api/v1/packages',
  idKey: 'package_id',
  paginated: false,
  newButtonLabel: 'New package',
  emptyTitle: 'No packages yet',
  emptyBody: 'This is a lightweight pricing catalog — separate from the full Service Plans used by Subscriptions & Billing.',
  columns: [
    { label: 'Package', render: r => `<div class="row-title">${escapeHtml(r.name)}</div><div class="row-sub mono">${escapeHtml(r.package_id)}</div>` },
    { label: 'Type', render: r => `<span class="badge badge-muted">${escapeHtml(r.package_type)}</span>` },
    { label: 'Speed', render: r => `${fmtNum(r.download_speed)}↓ / ${fmtNum(r.upload_speed)}↑ Mbps` },
    { label: 'Validity', render: r => `${fmtNum(r.duration_days)} days` },
    { label: 'Price', num: true, render: r => fmtMoney(r.price) },
    { label: 'Status', render: r => statusBadge(r.status || (r.is_active ? 'active' : 'inactive')) },
  ],
  formFields: (existing) => `
    ${Field.text('name', 'Package name', existing?.name || '', { required: true })}
    ${Field.select('package_type', 'Package type', ['home', 'hotspot'], existing?.package_type || 'home')}
    ${Field.row2(
      Field.text('download_speed', 'Download (Mbps)', existing?.download_speed || '', { type: 'number', required: true, min: 1 }),
      Field.text('upload_speed', 'Upload (Mbps)', existing?.upload_speed || '', { type: 'number', required: true, min: 1 })
    )}
    ${Field.row2(
      Field.text('price', 'Price (KES)', existing?.price || '', { type: 'number', required: true, min: 0, step: '0.01' }),
      Field.text('validity_days', 'Validity (days)', existing?.duration_days || 30, { type: 'number', required: true, min: 1 })
    )}
    ${Field.row2(
      Field.text('mikrotik_profile', 'MikroTik profile', existing?.mikrotik_profile || ''),
      Field.text('max_devices', 'Max devices', existing?.max_devices || 1, { type: 'number', min: 1 })
    )}`,
  toCreatePayload: (raw) => ({
    name: raw.name, package_type: raw.package_type,
    download_speed: Number(raw.download_speed), upload_speed: Number(raw.upload_speed),
    price: Number(raw.price), validity_days: Number(raw.validity_days),
    mikrotik_profile: raw.mikrotik_profile || null, max_devices: Number(raw.max_devices) || 1,
  }),
  toUpdatePayload: (raw) => ({
    name: raw.name, download_speed: Number(raw.download_speed), upload_speed: Number(raw.upload_speed),
    price: Number(raw.price), validity_days: Number(raw.validity_days),
    mikrotik_profile: raw.mikrotik_profile || null, max_devices: Number(raw.max_devices) || 1,
  }),
});
