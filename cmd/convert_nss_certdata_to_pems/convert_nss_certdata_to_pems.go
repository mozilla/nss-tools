/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

package main

import (
	"bufio"
	"bytes"
	"crypto/x509"
	"encoding/pem"
	"flag"
	"fmt"
	"os"
	"strconv"
)

var printHeaders = flag.Bool("headers", false, "Add PEM-headers to each block (not compatible with OpenSSL)")

// Create a custom split function by wrapping the existing ScanLines function.
func certDataSplit(data []byte, atEOF bool) (advance int, token []byte, err error) {
	advance, token, err = bufio.ScanLines(data, atEOF)
	if err == nil && token != nil {

		if bytes.HasPrefix(token, []byte("CKA_VALUE MULTILINE_OCTAL")) {
			endPos := bytes.Index(data, []byte("END"))

			if endPos > -1 {
				token = data[advance:endPos]
				advance = endPos + 3
				return
			}

			// Didn't find all our tokens, keep going
			advance = 0
			token = nil
			err = nil
			return
		}
		token = []byte{}

	}
	return
}

func processCertData(file *os.File) error {
	scanner := bufio.NewScanner(file)

	// Set the split function for the scanning operation.
	scanner.Split(certDataSplit)

	for scanner.Scan() {
		data := scanner.Text()
		if len(data) > 0 {
			var binBuf bytes.Buffer

			for pos := 0; pos+4 < len(data); pos += 4 {
				if data[pos] == '\n' {
					pos = pos + 1
				}

				ss := data[pos+1 : pos+4]
				i, err := strconv.ParseUint(ss, 8, 0)
				binBuf.WriteByte(byte(i))

				if err != nil {
					return err
				}
			}

			certObj, err := x509.ParseCertificate(binBuf.Bytes())
			if err != nil {
				return err
			}

			certBlock := pem.Block{
				Type:  "CERTIFICATE",
				Bytes: certObj.Raw,
			}

			// If desired, add PEM-comment headers (not compatible with OpenSSL)
			if *printHeaders {
				certBlock.Headers = map[string]string{
					"Issuer":        certObj.Issuer.CommonName,
					"Subject":       certObj.Subject.CommonName,
					"Serial Number": fmt.Sprintf("%036x", certObj.SerialNumber),
				}
			}

			err = pem.Encode(os.Stdout, &certBlock)
			if err != nil {
				return err
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("Invalid input: %s", err)
	}

	return nil
}

func main() {
	flag.Parse()
	if flag.NArg() != 1 {
		fmt.Println("You must specify the path to certdata.txt as the last argument")
		return
	}

	file, err := os.Open(flag.Arg(0))
	if err != nil {
		fmt.Println(err)
		return
	}

	err = processCertData(file)
	if err != nil {
		fmt.Println(err)
		return
	}

}
