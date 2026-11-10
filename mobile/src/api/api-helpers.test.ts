import { describeError, messageForCode } from './error-messages';
import { ApiError, NetworkError } from './errors';
import { withQuery } from './pagination';

describe('withQuery', () => {
  it('encodes parameters and drops empty values', () => {
    expect(withQuery('/jobs/', { search: 'a b', status: undefined, managed_by_me: true })).toBe(
      '/jobs/?search=a%20b&managed_by_me=true',
    );
    expect(withQuery('/jobs/', { search: '' })).toBe('/jobs/');
  });
});

describe('describeError', () => {
  it('explains network failures', () => {
    expect(describeError(new NetworkError())).toMatch(/offline/);
  });

  it('uses friendly wording for known codes', () => {
    expect(
      describeError(new ApiError(409, 'already_clocked_in', 'Already clocked in to J-1')),
    ).toBe(messageForCode('already_clocked_in'));
  });

  it('falls back to the server message for unknown codes', () => {
    expect(describeError(new ApiError(409, 'brand_new', 'Server says no'))).toBe('Server says no');
  });

  it('shows the first field error of a validation error', () => {
    const error = new ApiError(400, 'validation_error', 'Invalid input.', {
      job_number: ['This field must be unique.'],
    });
    expect(describeError(error)).toBe('job number: This field must be unique.');
  });
});
