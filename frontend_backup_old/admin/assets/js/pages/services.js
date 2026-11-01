Pages.services = makeSimpleCrudPage({
  title: 'Service plan',
  endpoint: '/api/v1/services',
  newButtonLabel: 'New service plan',
  emptyTitle: 'No service plans yet',
  emptyBody: 'Service plans are what Subscriptions & Billing actually bill against.',
  columns: [
    { label: 'Plan', render: r => `<div class="row-title">${escapeHtml(r.name)}</div><div class="row-sub mono">${escapeHtml(r.plan_code)}</div>` },
    { label: 'Type', render: r => `<span class="badge badge-muted">${escapeHtml(r.service_type)}</span>` },
    { label: 'Speed', render: r => `${fmtNum(r.download_speed_mbps)}↓ / ${fmtNum(r.upload_speed_mbps)}↑ Mbps` },
    { label: 'Cycle', render: r => escapeHtml(r.billing_cycle) },
    { label: 'Price', num: true, render: r => fmtMoney(r.base_price_kes) },
    { label: 'Status', render: r => statusBadge(r.status) },
  ],
  formFields: (existing) => `
    ${Field.row2(
      Field.text('plan_code', 'Plan code', existing?.plan_code || '', { required: !existing, disabled: !!existing }),
      Field.select('service_type', 'Service type', ['ftth', 'wireless', 'fiber', 'dsl', 'satellite'], existing?.service_type || 'ftth')
    )}
    ${Field.text('name', 'Plan name', existing?.name || '', { required: true })}
    ${Field.textarea('description', 'Description', existing?.description || '')}
    ${Field.row2(
      Field.text('download_speed_mbps', 'Download (Mbps)', existing?.download_speed_mbps || '', { type: 'number', required: true, min: 1 }),
      Field.text('upload_speed_mbps', 'Upload (Mbps)', existing?.upload_speed_mbps || '', { type: 'number', required: true, min: 1 })
    )}
    ${Field.row2(
      Field.text('base_price_kes', 'Monthly price (KES)', existing?.base_price_kes || '', { type: 'number', required: true, min: 0, step: '0.01' }),
      Field.select('billing_cycle', 'Billing cycle', ['monthly', 'quarterly', 'annually'], existing?.billing_cycle || 'monthly')
    )}
    ${Field.row2(
      Field.text('setup_fee_kes', 'Setup fee (KES)', existing?.setup_fee_kes ?? 0, { type: 'number', min: 0, step: '0.01' }),
      Field.text('data_cap_gb', 'Data cap (GB, blank = unlimited)', existing?.data_cap_gb ?? '', { type: 'number', min: 0 })
    )}`,
  toCreatePayload: (raw) => ({
    plan_code: raw.plan_code, name: raw.name, description: raw.description || undefined,
    service_type: raw.service_type, download_speed_mbps: Number(raw.download_speed_mbps),
    upload_speed_mbps: Number(raw.upload_speed_mbps), base_price_kes: Number(raw.base_price_kes),
    setup_fee_kes: Number(raw.setup_fee_kes) || 0, billing_cycle: raw.billing_cycle,
    data_cap_gb: raw.data_cap_gb ? Number(raw.data_cap_gb) : undefined,
  }),
  toUpdatePayload: (raw) => ({
    name: raw.name, description: raw.description || undefined,
    download_speed_mbps: Number(raw.download_speed_mbps), upload_speed_mbps: Number(raw.upload_speed_mbps),
    base_price_kes: Number(raw.base_price_kes), setup_fee_kes: Number(raw.setup_fee_kes) || 0,
    billing_cycle: raw.billing_cycle, data_cap_gb: raw.data_cap_gb ? Number(raw.data_cap_gb) : undefined,
  }),
});
