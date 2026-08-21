# The identity provider the API verifies against: Google's Firebase Auth emulator, which
# mints and signs tokens for a fake project with no credential of any kind. That is the
# whole reason it is here — a QA plan for this service has to hold *three* identities at
# once (two holders and an adjuster) and no fixture may ship a real one.
#
# firebase-tools is pinned because the emulator's token shape is what the API verifies:
# a version bump that changed the issuer or the claim envelope would break every trial at
# once, and it would look like an app defect.

FROM node:22-alpine
RUN apk add --no-cache openjdk17-jre-headless
RUN npm install --global firebase-tools@13.35.1
WORKDIR /srv
COPY auth/firebase.json auth/.firebaserc auth/seed.mjs ./
EXPOSE 9099
ENTRYPOINT ["firebase", "emulators:start", "--only", "auth", "--project", "claims-api-example"]
