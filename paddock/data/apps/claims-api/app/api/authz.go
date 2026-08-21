package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"

	firebase "firebase.google.com/go/v4"
	"firebase.google.com/go/v4/auth"
	"google.golang.org/api/option"

	"example.com/claims-api/gen"
)

// Identity is who the presented bearer token says the caller is. `Role` is read from the
// token's custom claims and defaults to `holder`, so a token minted with no role at all is
// the least-privileged caller rather than an unhandled case.
type Identity struct {
	UID  string
	Role string
}

// IsAdjuster reports whether the caller may act on someone else's claim.
func (i Identity) IsAdjuster() bool { return i.Role == "adjuster" }

type contextKey struct{}

// identityKey is the context key the middleware hands the verified caller down under.
var identityKey = contextKey{}

// Verifier is the slice of the Firebase Admin SDK this service uses, kept as an interface
// so the handlers can be exercised without an emulator in the loop.
type Verifier interface {
	VerifyIDToken(ctx context.Context, idToken string) (*auth.Token, error)
}

// Auth turns a bearer token into an Identity, or into a refusal.
type Auth struct {
	Verifier Verifier
}

// NewAuth builds the Admin SDK client. `option.WithoutAuthentication` is what makes the
// service startable with no service-account key on disk: against the emulator named by
// `FIREBASE_AUTH_EMULATOR_HOST` the SDK verifies the token's claims and skips the signature,
// and against a real project it would refuse to start rather than run half-authenticated.
func NewAuth(ctx context.Context, projectID string) (*Auth, error) {
	app, err := firebase.NewApp(ctx, &firebase.Config{ProjectID: projectID}, option.WithoutAuthentication())
	if err != nil {
		return nil, err
	}
	client, err := app.Auth(ctx)
	if err != nil {
		return nil, err
	}
	return &Auth{Verifier: client}, nil
}

// Require refuses any request the contract marks as secured and has no usable token for.
//
// Which requests those are is not a list kept here: the generated router puts
// `gen.BearerAuthScopes` in the context for exactly the operations `openapi.yml` secures,
// and `/healthz` — the one operation with `security: []` — arrives without it. Adding an
// endpoint to the document is therefore what protects it, and there is no second place to
// forget.
func (a *Auth) Require(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Context().Value(gen.BearerAuthScopes) == nil {
			next.ServeHTTP(w, r)
			return
		}
		raw, ok := bearerToken(r)
		if !ok {
			unauthorized(w, "The request carried no bearer token.")
			return
		}
		// VerifyIDToken is the whole of the check: signature (or, under the emulator, the
		// issuer), audience against this project, and expiry. There is no grace period on
		// any of the three — an expired token is a token the caller must replace.
		token, err := a.Verifier.VerifyIDToken(r.Context(), raw)
		if err != nil {
			unauthorized(w, "The bearer token was not accepted.")
			return
		}
		identity := Identity{UID: token.UID, Role: "holder"}
		if role, ok := token.Claims["role"].(string); ok && role != "" {
			identity.Role = role
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), identityKey, identity)))
	})
}

// caller returns the identity the middleware verified. A handler reached without one is a
// routing mistake rather than an anonymous request, so it is reported as a refusal instead
// of being served as some default caller.
func caller(r *http.Request) (Identity, bool) {
	identity, ok := r.Context().Value(identityKey).(Identity)
	return identity, ok
}

func bearerToken(r *http.Request) (string, bool) {
	header := r.Header.Get("Authorization")
	if len(header) < 7 || !strings.EqualFold(header[:7], "Bearer ") {
		return "", false
	}
	raw := strings.TrimSpace(header[7:])
	return raw, raw != ""
}

// unauthorized writes the one shape a refusal takes. `detail` is a sentence about the
// request, never anything out of it: the presented token is credential material, and a
// service that echoes it into a response body has also written it into every access log,
// proxy trace and bug report that response passes through.
func unauthorized(w http.ResponseWriter, detail string) {
	writeProblem(w, http.StatusUnauthorized, "Unauthorized", detail)
}

func writeProblem(w http.ResponseWriter, status int, title, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	body := gen.Problem{Title: title}
	if detail != "" {
		body.Detail = &detail
	}
	_ = json.NewEncoder(w).Encode(body)
}
