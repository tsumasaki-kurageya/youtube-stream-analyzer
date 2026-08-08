package youtube

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"time"
)

type ReservationMetadata struct {
	YouTubeVideoID   string
	ScheduledStartAt *time.Time
	ActualStartAt    *time.Time
	ActualEndAt      *time.Time
}

func (c *Client) FetchReservation(ctx context.Context, videoID string) (ReservationMetadata, error) {
	endpoint, err := url.Parse(c.baseURL + "/videos")
	if err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	query := endpoint.Query()
	query.Set("part", "liveStreamingDetails,status")
	query.Set("id", videoID)
	query.Set("key", c.apiKey)
	endpoint.RawQuery = query.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return ReservationMetadata{}, classifyHTTPError(resp)
	}
	var payload videosResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	if len(payload.Items) == 0 {
		return ReservationMetadata{}, &GatewayError{Code: CodeVideoNotFound}
	}
	item := payload.Items[0]
	result := ReservationMetadata{YouTubeVideoID: item.ID}
	if item.LiveStreamingDetails == nil {
		return result, nil
	}
	parse := func(value string) (*time.Time, error) {
		if value == "" {
			return nil, nil
		}
		parsed, err := time.Parse(time.RFC3339, value)
		if err != nil {
			return nil, err
		}
		return &parsed, nil
	}
	if result.ScheduledStartAt, err = parse(item.LiveStreamingDetails.ScheduledStartTime); err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	if result.ActualStartAt, err = parse(item.LiveStreamingDetails.ActualStartTime); err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	if result.ActualEndAt, err = parse(item.LiveStreamingDetails.ActualEndTime); err != nil {
		return ReservationMetadata{}, &GatewayError{Code: CodeTemporarilyUnavailable, Err: err}
	}
	return result, nil
}
