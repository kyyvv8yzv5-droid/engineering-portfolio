export const locationFieldNames = [
  "name", "address_line_1", "address_line_2", "city", "state", "postal_code",
  "country", "formatted_address", "phone", "website", "timezone",
] as const;

export type LocationFieldName = typeof locationFieldNames[number];
type FormValue = string | boolean;

export const locationPickerFieldMap: Record<string, LocationFieldName> = {
  name: "name", location_name: "name",
  address_line_1: "address_line_1", street_address: "address_line_1", addressLine1: "address_line_1",
  address_line_2: "address_line_2", addressLine2: "address_line_2",
  city: "city",
  state: "state", region: "state", administrative_area: "state", administrative_area_level_1: "state", province: "state", state_code: "state",
  postal_code: "postal_code", postalCode: "postal_code", zip: "postal_code", zip_code: "postal_code",
  country: "country", country_name: "country", country_code: "country", iso_country_code: "country",
  formatted_address: "formatted_address", formattedAddress: "formatted_address", address: "formatted_address",
  phone: "phone", phone_number: "phone", telephone: "phone",
  website: "website", website_url: "website", url: "website", provider_url: "website",
  timezone: "timezone", time_zone: "timezone", timezone_id: "timezone", timeZone: "timezone",
};

const countryCodes: Record<string, string> = {
  US: "United States", USA: "United States", CA: "Canada", CAN: "Canada",
  GB: "United Kingdom", GBR: "United Kingdom", MX: "Mexico", MEX: "Mexico",
};

function normalizeLocationValue(field: LocationFieldName, value: FormValue): FormValue {
  if (typeof value !== "string") return value;
  const cleaned = value.trim();
  if (field === "country") return countryCodes[cleaned.toUpperCase()] ?? (cleaned.length === 2 || cleaned.length === 3 ? cleaned.toUpperCase() : cleaned);
  if (field === "website" && cleaned && !cleaned.includes("://")) return `https://${cleaned}`;
  return cleaned;
}

export function normalizeLocationPickerUpdates(updates: Record<string, FormValue>): Partial<Record<LocationFieldName, FormValue>> {
  const normalized: Partial<Record<LocationFieldName, FormValue>> = {};
  for (const [sourceField, value] of Object.entries(updates)) {
    const targetField = locationPickerFieldMap[sourceField];
    if (targetField && value !== null && value !== undefined) normalized[targetField] = normalizeLocationValue(targetField, value);
  }
  return normalized;
}

export function applyLocationPickerUpdates(current: Record<string, FormValue>, updates: Record<string, FormValue>) {
  const normalized = normalizeLocationPickerUpdates(updates);
  const previous = Object.fromEntries(Object.keys(normalized).map((field) => [field, current[field] ?? ""]));
  return { next: { ...current, ...normalized }, previous, applied: normalized };
}

export function buildLocationSubmitPayload(form: Record<string, FormValue>) {
  return Object.fromEntries(Object.entries(form).map(([key, value]) => [key, typeof value === "string" && !value.trim() ? null : value]));
}
