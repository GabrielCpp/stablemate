// Command policy-desk serves the policy ledger API and the built web bundle from one
// process on one port. There is no reverse proxy and no second origin: a browser scenario
// and an HTTP scenario address the same service, so the two can never disagree about what
// is on file.
package main

import (
	"flag"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	addr := flag.String("addr", ":18084", "host:port to serve on")
	data := flag.String("data", "/data/policies.json", "path to the JSON policy ledger")
	web := flag.String("web", "/srv/web", "directory holding the built web bundle")
	flag.Parse()

	server := &Server{Store: &Store{Path: *data}}
	mux := http.NewServeMux()
	server.Routes(mux)
	mux.Handle("/", spa(*web))

	log.Printf("policy-desk listening on %s (ledger %s, bundle %s)", *addr, *data, *web)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("policy-desk stopped: %v", err)
	}
}

// spa serves the built bundle, falling back to index.html for any path that is not a file
// on disk. That fallback is what makes `/policies/pn-1001` a deep link rather than a 404:
// the router that owns the route lives in the bundle, and the bundle has to be delivered
// before it can read the URL.
//
// Two prefixes are held back from the fallback. An asset is a file or it is missing, and a
// bundle served in place of a missing script fails as a syntax error pointing at the wrong
// thing. `/api/` is held back for the same reason one step up: an unimplemented endpoint
// that answers 200 with a document reads, to anything checking a status, as an implemented
// one.
func spa(root string) http.Handler {
	files := http.FileServer(http.Dir(root))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name := filepath.Join(root, filepath.Clean("/"+r.URL.Path))
		if info, err := os.Stat(name); err == nil && !info.IsDir() {
			files.ServeHTTP(w, r)
			return
		}
		if strings.HasPrefix(r.URL.Path, "/assets/") || strings.HasPrefix(r.URL.Path, "/api/") {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, filepath.Join(root, "index.html"))
	})
}
