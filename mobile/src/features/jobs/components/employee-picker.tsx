import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { describeError } from '@/api/error-messages';
import { colors, QueryState, TextField } from '@/components/ui';
import { ROLE_LABELS, roleSchema } from '@/features/auth/schemas';

import { searchEmployees } from '../api';
import type { EmployeeOption } from '../schemas';

/**
 * Searchable list of active employees (Managers and Admins, decision M4).
 * The endpoint returns identity and account status only, never pay.
 */
export function EmployeePicker({
  role,
  selected,
  onToggle,
  disabledIds = new Set<number>(),
  disabledNote = 'Already assigned',
}: {
  role?: string;
  selected: Set<number>;
  onToggle: (employee: EmployeeOption) => void;
  disabledIds?: Set<number>;
  disabledNote?: string;
}) {
  const [search, setSearch] = useState('');
  const term = search.trim();
  const query = useQuery({
    queryKey: ['employees', { search: term, role }],
    queryFn: () => searchEmployees({ search: term || undefined, role, is_active: true }),
  });
  const employees = query.data?.results ?? [];

  return (
    <View style={styles.container}>
      <TextField
        label="Find employee"
        placeholder="Name or employee number"
        value={search}
        onChangeText={setSearch}
        autoCapitalize="none"
      />
      <QueryState
        isLoading={query.isPending}
        error={query.error ? describeError(query.error) : null}
        empty={query.isSuccess && employees.length === 0}
        emptyText="No matching employees."
      />
      {employees.map((employee) => {
        const disabled = disabledIds.has(employee.id);
        const checked = selected.has(employee.id);
        const account = employee.account
          ? ROLE_LABELS[roleSchema.parse(employee.account.role)]
          : 'No app account';
        return (
          <Pressable
            key={employee.id}
            testID={`employee-${employee.id}`}
            accessibilityRole="checkbox"
            accessibilityState={{ checked, disabled }}
            disabled={disabled}
            onPress={() => onToggle(employee)}
            style={[styles.row, disabled && styles.disabled]}
          >
            <Text style={[styles.box, checked && styles.boxOn]}>{checked ? '✓' : ''}</Text>
            <View style={styles.text}>
              <Text style={styles.name}>
                {employee.name}
                {employee.employee_number ? ` · ${employee.employee_number}` : ''}
              </Text>
              <Text style={styles.muted}>{disabled ? disabledNote : account}</Text>
            </View>
          </Pressable>
        );
      })}
      {query.data && query.data.count > employees.length ? (
        <Text style={styles.muted}>
          Showing {employees.length} of {query.data.count}. Search to narrow the list.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  disabled: { opacity: 0.5 },
  box: {
    width: 26,
    height: 26,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: colors.primary,
    textAlign: 'center',
    color: '#fff',
    fontWeight: '700',
  },
  boxOn: { backgroundColor: colors.primary },
  text: { flex: 1, gap: 2 },
  name: { fontSize: 16, color: colors.text },
  muted: { fontSize: 14, color: colors.muted },
});
