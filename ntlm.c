/* Simplified test case of lib/vauth/ntlm.c from libcurl 7.63.0
   Modified by Pavlo Pastaryev
 */

#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "klee/klee.h"

struct ntlmdata {
  void *target_info; /* TargetInfo received in the ntlm type-2 message */
  unsigned int target_info_len;
};

unsigned short Curl_read16_le(const unsigned char *buf) {
  return (unsigned short)(((unsigned short)buf[0]) | ((unsigned short)buf[1] << 8));
}

unsigned int Curl_read32_le(const unsigned char *buf)
{
  return ((unsigned int)buf[0]) | ((unsigned int)buf[1] << 8) |
         ((unsigned int)buf[2] << 16) | ((unsigned int)buf[3] << 24);
}

static int ntlm_decode_type2_target(unsigned char *buffer,
                                    size_t size,
                                    struct ntlmdata *ntlm)
{
  unsigned short target_info_len = 0;
  unsigned int target_info_offset = 0;

  if(size >= 48) {
  klee_assume(Curl_read16_le(&buffer[40]) > 0); // klee
  klee_assume(Curl_read32_le(&buffer[44]) >= 0); // klee
//    __CPROVER_ASSUME(Curl_read16_le(&buffer[40]) > 0); // cbmc
//    __CPROVER_ASSUME(Curl_read32_le(&buffer[44]) >= 0); // cbmc
    target_info_len = Curl_read16_le(&buffer[40]);
    target_info_offset = Curl_read32_le(&buffer[44]);
    if(target_info_len > 0) {
      if(((target_info_offset + target_info_len) > size) ||
         (target_info_offset < 48)) {
        return 1;
      }

      ntlm->target_info = malloc(target_info_len);
      if(!ntlm->target_info)
        return 2;

      memcpy(ntlm->target_info, &buffer[target_info_offset], target_info_len);
    }
  }

  ntlm->target_info_len = target_info_len;

  return 0;
}

int main() {
  unsigned char buff[256];

//  const char buff_test[] = "$buff"; // ikos
//  const char *p = buff_test; // ikos
//  int i = 0; // cbmc
//  for (int i = 0; i < sizeof(buff); i++) { // cbmc // ikos
//    sscanf(p, "%2hhx", &buff[i]); // ikos
//    buff[i] = nondet_uchar(); // cbmc
//  } // cbmc // ikos

  struct ntlmdata ntlm;

  klee_make_symbolic(&buff, sizeof(buff), "buff"); // klee
  klee_make_symbolic(&ntlm, sizeof(ntlm), "ntlm"); // klee

  ntlm_decode_type2_target(buff, sizeof(buff), &ntlm);
}