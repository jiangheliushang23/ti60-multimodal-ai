// GCC 13 emits __cxa_atexit registrations for static C++ objects. The vendor
// start.S replaces the normal CRT (-nostartfiles), so crtbegin.o does not
// supply its DSO identity. This single statically linked firmware image has
// one unique handle and no dynamic unloading; retain newlib's real atexit
// implementation rather than stubbing destructor registration.
extern "C" {
void* __dso_handle = &__dso_handle;
}
