Pages.sites = makeSimpleCrudPage({
  title: 'Site',
  endpoint: '/api/v1/sites',
  newButtonLabel: 'New site',
  emptyTitle: 'No sites yet',
  emptyBody: 'A site is a tower or POP location — routers, voucher batches and HotSpot plans can all be scoped to one.',
  columns: [
    { label: 'Site', render: r => `<div class="row-title">${escapeHtml(r.name)}</div><div class="row-sub mono">${escapeHtml(r.code)}</div>` },
    { label: 'Address', render: r => escapeHtml(r.address || '—') },
    { label: 'Contact', render: r => r.contact_person ? `${escapeHtml(r.contact_person)}<div class="row-sub">${escapeHtml(r.contact_phone || '')}</div>` : '—' },
    { label: 'Status', render: r => statusBadge(r.status) },
  ],
  formFields: (existing) => `
    ${Field.row2(
      Field.text('name', 'Site name', existing?.name || '', { required: true }),
      Field.text('code', 'Site code', existing?.code || '', { required: true, placeholder: 'NYR-001' })
    )}
    ${Field.text('address', 'Address', existing?.address || '')}
    ${Field.row2(
      Field.text('latitude', 'Latitude', existing?.latitude ?? '', { type: 'number', step: 'any' }),
      Field.text('longitude', 'Longitude', existing?.longitude ?? '', { type: 'number', step: 'any' })
    )}
    ${Field.row2(
      Field.text('contact_person', 'Contact person', existing?.contact_person || ''),
      Field.text('contact_phone', 'Contact phone', existing?.contact_phone || '')
    )}
    ${Field.select('status', 'Status', ['active', 'inactive', 'planned'], existing?.status || 'active')}
    ${Field.textarea('notes', 'Notes', existing?.notes || '')}`,
  toCreatePayload: (raw) => ({
    name: raw.name, code: raw.code, address: raw.address || undefined,
    latitude: raw.latitude ? Number(raw.latitude) : undefined, longitude: raw.longitude ? Number(raw.longitude) : undefined,
    contact_person: raw.contact_person || undefined, contact_phone: raw.contact_phone || undefined,
    status: raw.status, notes: raw.notes || undefined,
  }),
  toUpdatePayload: (raw) => ({
    name: raw.name, address: raw.address || undefined,
    latitude: raw.latitude ? Number(raw.latitude) : undefined, longitude: raw.longitude ? Number(raw.longitude) : undefined,
    contact_person: raw.contact_person || undefined, contact_phone: raw.contact_phone || undefined,
    status: raw.status, notes: raw.notes || undefined,
  }),
});
